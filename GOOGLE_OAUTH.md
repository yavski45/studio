# Activer la connexion Google de Dublao

1. Ouvre [Google Cloud Console](https://console.cloud.google.com/) et crée ou sélectionne un projet **Dublao**.
2. Ouvre **Google Auth Platform**. Clique sur **Get started / Premiers pas** si nécessaire.
3. Dans **Branding**, renseigne le nom **Dublao**, ton email d'assistance et ton email de contact.
4. Choisis une audience **External / Externe**. Pour le développement, conserve le mode **Testing / Test** et ajoute ton adresse Google dans **Audience → Test users / Utilisateurs de test**.
5. Dans **Clients → Create client / Créer un client**, choisis **Web application / Application Web** et nomme-le **Dublao local**.
6. Ajoute ces **URI de redirection autorisés**, avec le slash final :

```text
http://localhost:8000/comptes/google/login/callback/
http://127.0.0.1:8000/comptes/google/login/callback/
```

Le flux allauth est côté serveur : les origines JavaScript ne sont pas nécessaires.

7. Crée le client. Copie son **Client ID** et son **Client secret** directement dans le fichier local `.env` :

```dotenv
GOOGLE_OAUTH_CLIENT_ID=ton_client_id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=ton_client_secret
```

Ne les envoie pas dans le chat. Aucun objet SocialApp supplémentaire n'est nécessaire dans l'administration Django : les identifiants sont lus depuis `.env`.

8. Redémarre Django, ouvre `http://localhost:8000/comptes/login/`, puis clique sur **Continuer avec Google**. Le bouton s'active lorsque les deux variables sont remplies. Utilise un compte ajouté aux utilisateurs de test.

Si Google affiche `redirect_uri_mismatch`, compare exactement l'adresse avec les URI autorisés : hôte, port, chemin et slash final.

Pour la mise en ligne, ajoute l'URI HTTPS de ton domaine suivi de `/comptes/google/login/callback/`, complète le branding et ajuste l'audience dans Google Cloud.

## Emails et tests

En mode console, les emails de confirmation et de réinitialisation s'affichent dans le terminal Django. En mode SMTP, ils sont envoyés via le service configuré. La vérification email est obligatoire avant l'accès à l'espace. Une adresse certifiée par Google est reconnue via allauth.

Le départ OAuth est testé avec des identifiants fictifs. La connexion Google réelle doit être vérifiée après création du client.

## Documentation officielle

- [Créer des identifiants OAuth — Google](https://developers.google.com/workspace/guides/create-credentials)
- [OAuth pour les applications serveur — Google](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Configurer Google dans django-allauth](https://docs.allauth.org/en/latest/socialaccount/providers/google.html)
