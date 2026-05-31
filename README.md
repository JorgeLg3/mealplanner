# Mealprep App

This is the new I'm developing for my own use where I want to track the recipes I usually do. Organize the meal calendar of the following weeks. And auto generate the list of ingredients that I need to buy.

## Introduction
This is the codebase I have developed as template repo for future Django app developements. Including basic features and configurations ready to go
- Custom User model in case you need to customize the UserModel later on.
- Using SQLite in production. SQLite has shown enough performance with the proper settings to be used in production for a lot of use cases
- Using UV for project and dependencies management
- The app uses Docker to contain all the code and dependencies
- With the use of bind volumes for the `/media` and `/db-data` you can persist the app data while changing the app code.
- Whitenoise used for manage the staticfiles
- The migrate script is run as part of the Dockerfile entry script. While not ideal, it's safe enough with Django and perfectly valid for my use case. If you prefer to run it separately just remove that part of the `Dockerfile` and use something like: `docker compose run --rm django-app python manage.py migrate --noinput`
- Github workflows included the build the image and upload it to GH container registry
- Basic auth included. The reset/change password templates and backend email service can be customized for fully operational auth platform.
- Include user media support in production using nginx

## Local development
To run the Django server, first copy the `.example.env` and rename it to `.env`. And then change the values on your interest. The `SECRET_KEY` can be generated with `python3 -c "import secrets; print(secrets.token_urlsafe())"`

Then you can procede with the `docker compose up --build` to run the server inside a docker container that will serve the app in the port 8000 locally

To collect the staticfiles you can use the `uv run manage.py collectstatic`

You can run formatter, linter, type checker and tests with:
```
uv run ruff format
uv run ruff check
uv run ty check
uv run manage.py test
```

## Deployment
The `release.yml` workflow will build and push the docker image to Github container registry. From where you can later consume it. You can then create a production compose file with something like this:

```yaml
services:
  django-app:
    image: ghcr.io/jorgelg3/thejorgelab-blog:latest
    restart: unless-stopped
    volumes:
      - ./data/db-data:/app/db-data
      - ./data/media:/app/media
    environment:
      DEBUG: false
      SECRET_KEY: ${SECRET_KEY}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS}

  nginx:
    image: nginx:latest
    restart: unless-stopped
    ports:
      - "8001:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./data/media:/app/media
    depends_on:
      - django-app
```

You will then need to copy the [Nginx config file](nginx.conf) into the root folder from where you are serving the docker compose file.

And finally create a `.env` file next to your compose file to provide the environment variables (`SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) — see [`.example.env`](.example.env) for reference.