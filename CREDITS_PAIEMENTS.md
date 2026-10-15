# Portefeuille et Genius Pay

Achats ponctuels, sans abonnement ni reconduction automatique :

| Pack | Prix USD | Crédits | Prix moyen arrondi |
|---|---:|---:|---:|
| Starter | 10 $ | 11 | 0,91 $ |
| Creator | 25 $ | 28 | 0,89 $ |
| Pro | 50 $ | 57 | 0,88 $ |
| Business | 150 $ | 175 | 0,86 $ |
| Studio | 300 $ | 360 | 0,83 $ |

Le catalogue serveur est dans `credits/catalog.py`. Le navigateur ne fixe ni le
prix ni la quantité livrée. Les achats conservent leur propre tarif, même si le
catalogue change ensuite. Le portefeuille se consulte sur `/credits/`.

## Décompte du doublage

Un refus explicite de Murf pour `INSUFFICIENT_CREDITS` ou `CREDITS_EXHAUSTED`
met le doublage en `waiting_murf`. La vidéo reste stockée et la réservation
du portefeuille reste intacte : rien n'est consommé pendant l'attente.
Celery réessaie toutes les cinq minutes ; après recharge, l'acceptation par
Murf reprend le traitement, sans nouvelle réservation ni double débit.
Les demandes en attente sont comptées dans la limite de travaux actifs.
Le délai maximal de traitement commence à l'acceptation par Murf, pas à l'import.

Un job Murf définitivement refusé sans résultat ni crédit consommé est archivé
dans `murf_rejected_job_ids` avant la reprise. Un résultat partiel, une consommation
déjà signalée ou un envoi ambigu impose une vérification manuelle ; il n'est pas
reposté automatiquement. Les anciens doublages déjà marqués en échec ne sont pas
convertis rétroactivement en demandes de reprise.

Un crédit couvre une minute **entamée, par langue produite**, arrondie à la minute supérieure.
60 secondes coûtent un crédit ; 61 secondes coûtent deux crédits par langue.
Une vidéo de 80 secondes dans deux langues réserve quatre crédits ; une vidéo de
90 secondes dans deux langues réserve quatre crédits. Les réservations déjà créées
conservent leur montant, sans modification rétroactive. La durée est analysée
côté Celery avec FFprobe, à partir du fichier privé. Aucune durée transmise par
le navigateur n'est utilisée pour facturer.

La réservation précède l'envoi à Murf. Le solde disponible exclut les crédits
réservés. À la fin, seules les langues produites sont facturées ; les autres
réservations sont libérées. Un refus confirmé libère les crédits. Un envoi
dont la réception reste incertaine garde la réservation pour vérification,
et n'est jamais renvoyé automatiquement à Murf. Un échec de copie R2 garde
aussi la réservation jusqu'à récupération ou intervention.

Si le solde est insuffisant après analyse, aucun appel de création Murf n'est
effectué. La vidéo déjà importée peut être reprise après recharge. Les travaux
créés avant l'activation du portefeuille ne sont pas facturés rétroactivement.

## Configuration Genius Pay

Renseigner dans `.env`, sans envoyer les secrets dans un chat :

```dotenv
GENIUSPAY_API_KEY=
GENIUSPAY_API_SECRET=
GENIUSPAY_WEBHOOK_SECRET=
GENIUSPAY_WEBHOOK_SECRET_LIVE=
GENIUSPAY_WEBHOOK_SECRET_SANDBOX=
GENIUSPAY_ENVIRONMENT=sandbox
GENIUSPAY_ACCEPT_XOF_CONVERSION=true
PAYMENT_PUBLIC_URL=http://127.0.0.1:8000
CREDITS_ENABLED=true
```

Les clés API se trouvent dans Genius Pay, **Paramètres → API**. Commencer par
les clés sandbox. Le code utilise l'API Marchand officielle et son checkout
hébergé ; les moyens disponibles dépendent du compte Genius Pay.

`GENIUSPAY_MODE` (nom du guide webhook) est également accepté si
`GENIUSPAY_ENVIRONMENT` n'est pas défini. Si les deux sont présents, ils doivent
avoir la même valeur. Le mode ne change jamais d'après une notification reçue.
Le module `credits/config.py` lit les variables chargées depuis `.env` même
si leurs alias ne sont pas déclarés dans `settings.py`. Les réglages Django
explicites restent prioritaires. Les préfixes des deux clés API doivent
correspondre au mode actif ; une paire live n'est pas utilisée en sandbox.

## Parcours des prochaines tentatives

Sur `/credits/`, l'utilisateur choisit un pack puis **Payer avec Genius Pay**.
Dublao crée l'achat avec le prix du catalogue et les métadonnées d'identification,
puis demande une `checkout_url`, sans imposer de moyen de paiement.
Le client choisit et paie sur la page Genius Pay. Reposter le même formulaire
ne crée pas une deuxième demande de paiement.

Pour les nouveaux checkouts, `success_url` et `error_url` pointent vers
`/credits/callback/?purchase=IDENTIFIANT_ACHAT`. Cette route authentifiée vérifie l'achat
auprès de Genius Pay puis redirige toujours vers `/credits/`, après succès,
échec, annulation ou retour avec une confirmation encore en attente.
Le portefeuille affiche un message correspondant à l'état vérifié.
Les paramètres de l'URL ne peuvent jamais confirmer un paiement.
L'adresse fixe `http://127.0.0.1:8000/credits/callback/`, sans identifiant,
permet également de revenir au portefeuille, sans confirmer ni créditer d'achat.
L'ancienne route `/credits/retour/IDENTIFIANT_ACHAT/` reste compatible.

Les checkouts déjà créés conservent leurs anciennes URL chez Genius Pay.
Ces anciennes URL sont également traitées comme des retours : vérification
serveur puis redirection vers le portefeuille. Les fiches d'achat restent
accessibles depuis l'historique via `?details=1`. Sur une fiche encore en attente,
HTMX lance une vérification serveur unique.
Le serveur consulte la transaction avec les clés API, contrôle l'identité,
le montant, la devise et l'environnement, puis ajoute les crédits une seule fois
si l'état est `completed`. Sans JavaScript, le bouton **Vérifier le paiement**
reste utilisable. Une réponse encore en attente permet une vérification manuelle ;
Celery continue également la réconciliation toutes les cinq minutes.
La vérification HTMX redirige également vers le portefeuille si un paiement
réussi ou non abouti est confirmé. Fermer un onglet, ou quitter une page sans
utiliser le retour proposé par Genius Pay, ne déclenche aucune redirection.

Un refus explicite d'authentification ou de validation (HTTP 401, 403, 422)
classe cette tentative comme non aboutie. **Réessayer l'achat** revient au même
pack avec un nouveau formulaire. Une réponse réseau incertaine ou incohérente
passe en vérification, sans renvoyer automatiquement une création de paiement.
Une référence reçue de la création authentifiée est conservée. Si la réponse
de création n'inclut pas les métadonnées ou l'environnement, le serveur relit
immédiatement cette référence avant de proposer le checkout.

Le motif technique est consultable dans l'administration (`error_code`). Les
logs ne conservent que l'identifiant d'achat, le statut HTTP, un code d'erreur
connu et les noms des champs rejetés, jamais les messages ou corps de l'API.

## Devise et notifications

Les requêtes demandent explicitement `currency=USD`, avec le prix du pack en
dollars. La conversion en FCFA est effectuée par Genius Pay, sans taux fixé
dans Dublao. `GENIUSPAY_ACCEPT_XOF_CONVERSION=true` autorise cette conversion,
conformément au choix du marchand. Le prix USD et la quantité de crédits restent
ceux du catalogue. La création authentifiée fixe le montant XOF, sa devise et
`quoted_at` avant de rediriger le client ; un montant XOF doit être positif,
comporter au plus deux décimales et provenir d'une transaction encore en attente
de paiement. `quoted_amount` conserve exactement ce montant sous forme Decimal,
sans arrondi. Exemple : une conversion à 5 220,50 FCFA ne devient ni 5 220
ni 5 221 FCFA. Les anciennes écritures restent lisibles via `amount_minor`.

Les webhooks et confirmations ultérieures doivent correspondre exactement à
ce montant enregistré. Ils ne peuvent jamais établir ni modifier une conversion.
Une quote déjà enregistrée ne change plus. Si l'API retourne USD, le montant
doit rester exactement le prix USD du pack. La page d'achat affiche le montant
FCFA reçu de Genius Pay, et le portefeuille prévient le client de la conversion.
Sans activation de cette option, une réponse XOF est bloquée. Le fonctionnement
réel de création et d'encaissement dépend toujours du compte Genius Pay.

Pour les notifications automatiques, déclarer dans Genius Pay :

```text
https://votre-domaine/credits/webhook/geniuspay/
```

Événements : `payment.success`, `payment.failed`, `payment.cancelled`,
`payment.expired`, `payment.refunded`. Conserver le secret `whsec_...` dans
`GENIUSPAY_WEBHOOK_SECRET_LIVE` pour le mode live, ou
`GENIUSPAY_WEBHOOK_SECRET_SANDBOX` pour les tests. La variable générique
`GENIUSPAY_WEBHOOK_SECRET` reste acceptée en remplacement.

En local, Genius Pay ne peut pas joindre
`127.0.0.1` ; la page de retour offre un bouton **Vérifier le paiement**,
qui consulte l'API côté serveur. Celery vérifie également les achats dont la
référence est connue toutes les cinq minutes, pendant sept jours.

Le webhook vérifie le HMAC sur le corps brut et un timestamp récent, puis
enregistre durablement la notification avant de répondre HTTP 200. L'environnement
est lu à la racine du JSON, conformément au guide, et doit correspondre au mode
actif. `X-Webhook-Event` est obligatoire et doit correspondre au corps. Une
signature incorrecte donne HTTP 401 ; une notification expirée ou mal formée
donne HTTP 400. `webhook.test` répond 200 sans toucher aux crédits.

Le handler HTTP ne contacte ni Redis ni Genius Pay : il ne dépend donc pas du
temps de réponse de leur réseau pour respecter la limite de dix secondes.
Beat publie les notifications en attente toutes les trente secondes et Celery
relit la transaction avec les clés marchand. Montant, devise, environnement,
référence et métadonnées doivent correspondre à l'achat. Une livraison répétée
ne crédite jamais deux fois. Un simple retour navigateur n'ajoute aucun crédit.

Si l'API est indisponible ou ne confirme pas encore un paiement ou remboursement,
la notification est réessayée avec temporisation, jusqu'à vingt tentatives.
Les interruptions de worker sont reprises après expiration du verrou temporaire.
Une réponse incohérente passe en vérification manuelle. Les notifications se
consultent dans Django Admin ; leurs logs contiennent l'identifiant interne,
l'événement et le statut. Les corps JSON, numéros de téléphone, signatures et
secrets ne sont pas enregistrés. Seules les références nécessaires et l'empreinte
du corps signé sont conservées.

**Un paiement sandbox n'ajoute aucun crédit utilisable chez Murf.** Sa page
affiche le succès du test. Les soldes réels restent distincts des tests. Les
remboursements confirmés gèlent le portefeuille pour vérification comptable :
les crédits peuvent avoir été déjà consommés. Aucun remboursement monétaire
n'est émis par cette intégration.

Après changement de `.env` : recréer les services pour charger les variables :

```powershell
docker compose up -d --build worker beat
```

## Administration et vérifications

Les soldes, réservations, achats et écritures sont consultables en lecture
seule dans Django Admin. Ne pas modifier directement un solde. Pour un geste
commercial explicitement décidé, utiliser une référence unique :

```powershell
env\Scripts\python.exe manage.py grant_credits --user-id 123 --credits 5 --reference geste-2026-001 --reason "Geste commercial validé"
```

Répéter cette commande avec la même référence n'ajoute pas les crédits deux
fois. Aucun crédit gratuit n'est ajouté à la création d'un compte.

```powershell
env\Scripts\python.exe manage.py test credits studio comptes --settings=dublao.test_settings --noinput
```

Ces tests isolés simulent les réponses de paiement et Murf. Ils vérifient les
montants, réservations, résultats partiels, signatures, contrôles d'accès et
doublons. SQLite ne vérifie pas la concurrence réelle des verrous PostgreSQL.
Les écritures de production utilisent des transactions et verrous de ligne.

Vérification du handler avec le secret réellement configuré, sans API externe ni
modification des soldes :

```powershell
env\Scripts\python.exe manage.py check_genius_webhook
```

Ce contrôle local ne prouve pas la livraison depuis Internet. Pour celle-ci,
utiliser le bouton de test du webhook dans le tableau de bord Genius Pay et
vérifier le HTTP 200 sur l'URL HTTPS publique. Redémarrer Django et les conteneurs
après modification du mode ou des secrets dans `.env`.
Après modification du code Python, recréer également worker et beat pour
recharger leurs modules (Django utilise son rechargement automatique en local).

Une tentative non payée rejetée par l'ancien contrôle entier peut être rouverte
avec la commande suivante, après vérification authentifiée de son état `pending`,
de son identité et de son montant. Elle ne crée aucune transaction ni écriture
de crédit, et refuse un achat déjà payé, remboursé ou dont la quote a été fixée :

```powershell
env\Scripts\python.exe manage.py recover_genius_checkout IDENTIFIANT_ACHAT
```

Références : [API Genius Pay](https://geniuspay.ci/docs/api),
[FFprobe](https://ffmpeg.org/ffprobe.html).
