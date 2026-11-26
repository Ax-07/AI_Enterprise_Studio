# V3.0.2 — Déploiement Git contrôlé (projet V03 déjà rattaché)

Statut : procédure candidate, à valider avant livraison. Le moteur conserve VERSION 3.0.0 ; le cycle V3.0.2 désigne le développement du campus. Le commit exact et les résultats de CI identifient la livraison. Ne pas exécuter cette procédure sur un brouillon.

## Conditions de bascule

- PR #31 validée et fusion autorisée séparément ; contrôler les résultats du commit livré, y compris Chromium, préservation V2, migration isolée, sandbox et intégrations. Ne pas prendre un commit de préparation pour une livraison.
- Dépôt racine existant, V03 déjà suivie dans Git, branche locale main. Aucun changement suivi local, aucune divergence avec le commit distant livré, aucun fichier privé suivi. Ne pas utiliser reset --hard, clean, stash -u, git add global ni supprimer un dossier de sauvegarde.
- Arrêter proprement toutes les missions, campagnes et autorisations actives si nécessaire, fermer le serveur et le service TEST, vérifier les processus et ports 8790/8765. Une absence de port ouvert ne prouve pas seule l'arrêt de tous les processus.
- Vérifier la disponibilité d'espace pour une copie complète ; emplacement privé hors dépôt, hors synchronisation cloud et sur stockage accessible uniquement au propriétaire. Une sauvegarde locale ne remplace pas une sauvegarde externe indépendante.

## Sauvegarde et vérification (PowerShell, dépôt racine)

Ces commandes constituent un modèle de procédure à exécuter uniquement après autorisation de livraison. Laisser les serveurs arrêtés pendant toute la copie. Aucun secret ne doit être envoyé au chat ou à GitHub.

~~~powershell
$ErrorActionPreference = 'Stop'
if ((git branch --show-current) -ne 'main') { throw 'Branche locale incorrecte' }
$trackedStatus = git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $trackedStatus) { throw 'État Git non confirmé ou modifications suivies présentes' }
$trackedPrivate = git ls-files -- AI_Enterprise_Studio_V03/config.json AI_Enterprise_Studio_V03/donnees
if ($LASTEXITCODE -ne 0 -or $trackedPrivate) {
    throw 'Données privées suivies : arrêt'
}
$old = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'HEAD non disponible' }
$src = (Resolve-Path -LiteralPath 'AI_Enterprise_Studio_V03').Path
if (-not (Test-Path -LiteralPath (Join-Path $src 'donnees\enterprise.sqlite3') -PathType Leaf)) {
    throw 'Base absente'
}
$backupRoot = Join-Path $env:LOCALAPPDATA 'AIEnterpriseStudio\Backups'
$dst = Join-Path $backupRoot ('V03-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $old.Substring(0,8))
if (Test-Path -LiteralPath $dst) { throw 'Destination existante' }

function Get-PrivateManifest([string]$root) {
    $entries = Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction Stop
    if ($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
        throw 'Lien ou point de réanalyse : examen requis avant copie'
    }
    @($entries | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
        $relative = $_.FullName.Substring($root.Length + 1)
        [pscustomobject]@{ Path = $relative; Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    } | Sort-Object Path)
}
$before = Get-PrivateManifest $src
New-Item -ItemType Directory -Path $dst -Force | Out-Null
robocopy $src $dst /E /XJ /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Copie incomplète : conserver source et copie, arrêter' }
$copy = Get-PrivateManifest $dst
$after = Get-PrivateManifest $src
if ((Compare-Object $before $copy -Property Path,Hash) -or
    (Compare-Object $before $after -Property Path,Hash)) {
    throw 'Empreintes divergentes : aucune bascule'
}
py -3 -c "import sqlite3,sys,pathlib; p=pathlib.Path(sys.argv[1]).resolve(); c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]; c.close()" (Join-Path $dst 'donnees\enterprise.sqlite3')
if ($LASTEXITCODE -ne 0) { throw 'Intégrité SQLite non confirmée' }
Write-Host 'Copie locale vérifiée ; aucune mise à jour ni aucun serveur démarré.'
~~~

Le contrôle porte sur les fichiers copiés et SQLite, pas sur une restauration fonctionnelle complète. Les données supplémentaires, notamment le stockage TEST, restent au même emplacement dans l'installation. Si PowerShell, Python, Git ou les chemins ne correspondent pas, s'arrêter : ne pas contourner un échec. Un fichier OneDrive non hydraté ou un point de réanalyse peut provoquer un refus ; vérifier localement la disponibilité des fichiers et le type de lien avant de reprendre. Ne pas désactiver le contrôle. Aucun script de copie ne remplace la confirmation que toutes les écritures sont arrêtées.

## Mise à jour après livraison (pas avant)

Le commit attendu doit être fourni avec le bilan de livraison et correspondre à origin/main, pas au HEAD d'une PR brouillon. Depuis la racine, avec les serveurs arrêtés et la sauvegarde vérifiée :

~~~powershell
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch échoué' }
# Remplacer uniquement par le SHA exact validé lors de la livraison.
$expected = 'SHA_DE_LIVRAISON_A_CONFIRMER'
if ($expected -notmatch '^[0-9a-f]{40}$') { throw 'Commit de livraison non confirmé' }
if ((git rev-parse origin/main).Trim() -ne $expected) { throw 'Commit distant différent' }
git merge-base --is-ancestor HEAD $expected
if ($LASTEXITCODE -ne 0) { throw 'Historique divergent : aucune bascule' }
$trackedStatus = git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $trackedStatus) { throw 'État Git non confirmé ou changements locaux' }
git merge --ff-only --no-overwrite-ignore $expected
if ($LASTEXITCODE -ne 0) { throw 'Mise à jour refusée' }
if ((git rev-parse HEAD).Trim() -ne $expected) { throw 'HEAD différent' }
~~~

Recontrôler avant démarrage la présence des fichiers de donnees/ et de config.json s'il existait, ainsi que leurs empreintes par rapport à la copie. Ne pas lancer prepare_update.py sur la V03 déjà suivie : ce script est réservé à une installation parallèle neuve. Ne pas renommer le dossier V03 ni déplacer les données TEST.

## Aperçu puis décision de mise en service

Depuis V03, LANCER_DESIGN.bat ouvre le campus original en lecture seule via preview_campus.py --original. Vérifier la navigation, les historiques, les coûts, les livrables et l'absence de commandes ; comparer les données à l'état avant mise à jour. Fermer l'aperçu. Lancer Demarrer_Enterprise.bat uniquement après décision du propriétaire : le serveur normal peut reprendre les services périodiques existants selon leurs autorisations. Aucune dépense réelle ne doit être déduite d'un aperçu ni autorisée implicitement par la mise à jour.

## Repli

Avant toute nouvelle écriture : fermer les serveurs, conserver les deux états, vérifier les empreintes et préparer un repli de code compatible avec la base inchangée. Ne pas exécuter de reset destructif. Après nouvelles écritures, engagements ou dépenses : ne jamais restaurer automatiquement une ancienne base. Rapprocher les registres et autorisations ; valider une procédure dédiée. Conserver toutes les sauvegardes privées. Aucun transfert de secret, aucune fusion et aucun démarrage n'ont été réalisés par ce document.
