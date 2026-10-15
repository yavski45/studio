# Emails de réinitialisation Dublao

Le lien « Mot de passe oublié ? » est disponible sur `/comptes/login/`. Le formulaire demande l'adresse du compte et envoie un lien permettant de choisir un nouveau mot de passe. Un lien utilisé ne peut plus servir une seconde fois.

## Confirmation de l'adresse et interface

La confirmation se fait depuis le lien reçu par email. L'ancienne page de gestion `/comptes/email/` redirige vers l'espace compte.

Les messages de confirmation (inscription et renvoi) et de réinitialisation partagent un design HTML Dublao avec une version texte. Les pages de lien de confirmation et de mail envoyé utilisent le style du site.

L'aperçu de présentation `preview/confirmation-email.html` utilise un lien fictif. Il se régénère avec `env/Scripts/python.exe -m preview.render_emails` et ne doit pas servir à envoyer des emails.

## Activer un serveur SMTP

Les variables suivantes sont préparées dans `.env`. Remplace les valeurs ci-dessous par celles de ton service mail. Conserve `EMAIL_DELIVERY=console` tant que les identifiants ne sont pas prêts.

```dotenv
EMAIL_DELIVERY=smtp
EMAIL_HOST=smtp.ton-service.example
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_HOST_USER=ton_adresse_mail
EMAIL_HOST_PASSWORD=ton_identifiant_secret_smtp
DEFAULT_FROM_EMAIL="Dublao <ton_adresse_mail>"
```

Le nom `.example` est un exemple, pas un serveur à utiliser. L'expéditeur doit être une adresse autorisée par le fournisseur SMTP. Avec SSL sur le port 465, utilise `EMAIL_USE_TLS=false` et `EMAIL_USE_SSL=true`.

Les secrets restent dans `.env`, jamais dans le chat. Redémarre Django après modification de ce fichier.

## Vérifier la réception

### Gmail : erreur d'authentification 535

Cette erreur signifie que Gmail refuse l'authentification SMTP. Vérifie que le mot de passe d'application a été généré dans le compte Google correspondant exactement à `EMAIL_HOST_USER`.

1. Ouvre [les mots de passe d'application Google](https://myaccount.google.com/apppasswords) et vérifie le compte sélectionné en haut à droite.
2. La validation en deux étapes doit être active. Crée un nouveau mot de passe d'application pour Dublao.
3. Copie uniquement les 16 caractères du secret dans `EMAIL_HOST_PASSWORD`, sans les espaces de présentation. Ne modifie pas le mot de passe de ton compte Google.
4. Redémarre Django après modification de `.env`.

Si le mot de passe habituel du compte Google a été changé, les anciens mots de passe d'application sont révoqués. [Aide Google](https://support.google.com/accounts/answer/185833?hl=fr).

### Réception dans la boîte mail

1. Ouvre `/comptes/password/reset/`.
2. Indique l'adresse d'un compte Dublao existant.
3. Consulte la boîte mail et les indésirables.
4. Ouvre le lien, saisis le nouveau mot de passe deux fois, puis reconnecte-toi.

Cette opération change le mot de passe du compte Dublao. Elle ne change pas celui du compte Google. Le mode console affiche les messages dans le terminal et n'envoie aucun email réel.

Le formulaire affiche la même confirmation pour les adresses existantes et inexistantes afin de ne pas dévoiler les comptes. Une confirmation seule ne prouve donc pas que l'email a été reçu.

La vérification email est obligatoire. Après l'inscription, l'utilisateur attend sur la page de confirmation et ne peut pas accéder à l'espace avant validation du lien. Dans le même navigateur, la validation reprend la connexion et redirige vers l'espace. Dans un autre navigateur, il faut se connecter après validation.

En cas de panne SMTP, l'inscription affiche une erreur explicite et annule la création du nouveau compte. Un compte existant non vérifié reste bloqué. La réinitialisation affiche aussi une erreur si son envoi échoue. Les comptes déjà créés ne sont pas supprimés et leurs adresses ne sont pas automatiquement validées.

## État de la vérification

Les tests isolés vérifient le destinataire, le sujet Dublao, le contenu HTML et texte, le changement du mot de passe et l'invalidation du lien utilisé. La configuration du backend SMTP est vérifiée sans connexion réseau. La réception réelle reste à vérifier après ajout des identifiants du fournisseur.

[Documentation email Django 6.1](https://docs.djangoproject.com/en/6.1/topics/email/)
