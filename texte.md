super — tu veux permettre à chaque établissement d’**importer sa liste d’étudiants** (Excel/CSV) même si les colonnes ne sont pas les mêmes d’une école à l’autre. On reste côté **modèles** (design de données), pas encore dans le code : je t’explique l’architecture à mettre en place pour que ce soit **souple, multi-tenant, robuste, performant**.

# L’idée clé

Séparer l’import en **deux couches** :

1. **Staging** (tampon) : on stocke *tel quel* le fichier et ses lignes “brutes” + une version **normalisée** temporaire, **par établissement**.
2. **Commit** (intégration) : après validation, on transforme ces lignes staging en **User (role=student)** + **StudentProfile** réels dans le tenant.

\=> Grâce à ça, tu acceptes **n’importe quelles en-têtes colonnes**, tu crées une **correspondance (mapping)** par établissement, tu valides, puis tu intègres.

# Les modèles (concepts) à prévoir

Tous **scopés tenant** (FK vers `EstablishmentProfile`), pour isoler les données.

1. **ImportBatch** (lot d’import)

* Qui ? `establishment`, `created_by_user`
* Quoi ? `source_type` (csv/xlsx), `original_filename`, `school_year` (année scolaire du lot), options (ex. dédoublonnage par email/phone/matricule)
* État : `status` (uploaded → mapped → validated → ready\_to\_commit → committed → failed), compteurs (lignes OK/erreur), timestamps
* Liens : `mapping` utilisé, `files` (voir ImportFile)

2. **ImportFile** (les fichiers bruts)

* FK `batch`
* `file` (FileField), `checksum` (intégrité), `mime_type`, `encoding`, `delimiter` (si CSV), `sheet_name` (si Excel), `rows_count`, `headers` (liste)

3. **ImportMapping** (gabarit de correspondance par établissement)

* FK `establishment`
* `name`, `version`
* **`field_mappings` (JSON)** : comment chaque colonne source mappe vers un champ cible de la plateforme (ex. “Nom Élève” → `full_name`, “Mail” → `email`, “Téléphone tuteur 1” → `parent_phone_1`, “Niveau” → `level_external_code`, etc.)
* **`transforms` (JSON)** : petites règles de transformation déclaratives (trim, upper/lower, concat prénom/nom → full\_name, normalisation E.164, parsing date `DD/MM/YYYY` → ISO, etc.)
* **`aliases` (JSON)** : dictionnaire d’alias d’en-têtes pour auto-détection (ex. `{"mail":["email","e-mail","adresse mail"]}`)
* `required_targets` : liste des champs cibles obligatoires pour valider une ligne (ex. au moins **un identifiant fort** parmi `email` | `phone` | `matricule`)

4. **StagingStudentRow** (une ligne importée, **par batch**)

* FK `batch`
* **`row_index`** (position dans le fichier), **`raw` (JSON)** (clé = nom de colonne du fichier, valeur brute)
* **`normalized` (JSON)** : après application du mapping + transforms (clé = champ cible plateforme)
* **`status`** : pending / normalized / error / valid
* **`errors` (liste JSON)** : codes + messages champs invalides
* **`row_hash`** : hash de la ligne normalisée pour l’idempotence (éviter re-création multiple)
* Index : `(batch, status)`, `row_hash`

5. **ImportError** (optionnel si tu ne veux pas stocker les erreurs dans la ligne)

* FK `staging_row`, `field`, `code`, `message`, `severity` (warning/error)

6. **ImportCommitLog** (journal d’intégration)

* FK `batch`
* `created_users`, `updated_users`, `skipped`, `duplicate_strategy_used` (ex. merge/skip)
* `duration_ms`, `preview_sample` (extraits)

> Optionnel (utile) : **LookupCache** par établissement pour résoudre rapidement les références externes (ex. trouver `Level` ou `Department` par code/alias venant du fichier), afin de ne pas requêter la DB à chaque ligne.

# Flux d’import (étapes)

1. **Upload** : l’école envoie CSV/XLSX → **ImportBatch** + **ImportFile** créés (tenant = établissement).
2. **Sniff & analyse** : tu détectes type/encoding/headers ; tu proposes un **mapping** en te basant sur `aliases`.
3. **Choix/édition du mapping** : l’admin du tenant sélectionne un mapping existant (ou ajuste les correspondances).
4. **Normalisation** (staging) :

   * Pour chaque ligne : appliquer `field_mappings` + `transforms`.
   * Remplir `normalized`.
   * **Valider** (formats d’emails, E.164, date de naissance pas future, unicité matricule par établissement, année scolaire `YYYY-YYYY`, etc.).
   * Marquer `status` valid/error + stocker `errors` lisibles.
5. **Prévisualisation** : l’admin voit les stats (lignes valides / en erreur), télécharge les erreurs si besoin, corrige son fichier ou ajuste le mapping.
6. **Commit** : en tâche **asynchrone** (Celery) et **par paquets** (bulk):

   * Dédoublonnage (selon stratégie du batch) : priorité `email` > `phone` > `(establishment, matricule)`.
   * **Upsert** :

     * si user existe (email/phone trouvé dans le tenant) → **update** du `StudentProfile`.
     * sinon **create** `User(role=student, establishment=…)` + `StudentProfile` (avec `current_school_year`).
   * Respecter contraintes DB (unicité `(establishment, matricule)`) et tenir un **journal** (ImportCommitLog).
7. **Post-traitements** : invitations email/SMS (si activé), export du rapport, purge du staging (ex. 30 jours).

# Pourquoi c’est flexible

* **Mappings par établissement** : chaque école peut avoir **son** format ; tu gardes leur template et tu le réutilises.
* **Transforms déclaratives** : tu gères les petites différences (format date, nom concaténé, majuscules/minuscules, normalisation téléphone) **sans changer le code**.
* **Staging résilient** : tu acceptes même des fichiers imparfaits, tu listes les erreurs précisément **par ligne** avant d’intégrer.

# Contraintes & sécurité (importantes)

* **Multi-tenant** : toutes les tables ci-dessus ont FK `establishment` (directe ou via `batch.establishment`). Aucun batch n’accède aux données d’un autre tenant.
* **Idempotence** : `row_hash` + `batch_id` → si on relance, on ne duplique pas.
* **Dédoublonnage contrôlé** : stratégie du batch (merge/skip/fail) pour collisions sur email/phone/matricule.
* **PII** : le staging contient des données sensibles → **rétention courte** (ex. purge automatique à J+30), accès restreint, logs d’audit.
* **Traçabilité** : `X-Request-Id`, timestamps, `ImportCommitLog`, compteur par action.
* **Perf** : parsing en flux, **bulk\_create / bulk\_update** (ex. paquets de 1k), caches de lookup (levels, departments), workers Celery parallèles avec **verrou par tenant** pour éviter les courses.

# Champs cibles typiques (dictionnaire plateforme)

Tu définis une **liste canonique** de champs étudiants que les mappings peuvent cibler :

* Identité minimales : `full_name`, `email`, `phone` *(au moins un requis)*, `matricule` *(souvent requis par établissement)*
* Scolarité : `current_school_year`, `level_code` / `level_name`, `department_code` / `department_name`
* Infos perso : `date_of_birth`, `address`, `parent_name_1`, `parent_phone_1`, `parent_name_2`, `parent_phone_2`

> Les codes `level_code`/`department_code` servent à **faire le pont** avec tes tables `Level`/`Department` du tenant (via cache/lookup).

# Règles de validation (exemples)

* **Année scolaire** : format `YYYY-YYYY` et `YYYY2 = YYYY1 + 1`.
* **Téléphones** : E.164 + préfixes **CEMAC**.
* **Date naissance** : non future, âge minimal ? (optionnel par tenant).
* **Matricule** : non vide et **unique** dans le tenant.
* **Email** : syntaxe valide, normalisé en minuscule.
* **Niveau/Filière** : résolus par code/alias dans le **même tenant**, sinon erreur claire.

# Qu’est-ce qui change côté modèles existants ?

Rien dans `User` et `StudentProfile` : on **alimente** ces modèles à l’étape **Commit**.
Tout l’effort d’adaptation se fait dans les **modèles d’import** (*ImportBatch*, *ImportMapping*, *StagingStudentRow*, …) qui restent **internes** et protègent tes données métier.

---

si ça te va, je peux te proposer ensuite :

* la **liste exacte des champs** et index de chacun de ces modèles,
* puis le **code des modèles** complet et documenté,
* et (optionnel) une **commande de management** pour lancer un import + un **service** d’auto-détection de mapping (basé sur les alias).
