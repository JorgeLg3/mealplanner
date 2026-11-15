# Mealprep App

This is the app I'm developing for my own use at home. I want to keep track of the recipes we usually cook, organize the meal calendar of the following weeks, and auto generate the list of ingredients we need to buy. It's a shared household app, so everybody logged in sees and edits the same recipes, calendar and todos. The project is divided in three apps:
- Recipes: like a cookbook we can create recipes with ingredients, servings, a description and an optional photo. Recipes and ingredients are grouped by categories.
- Planner: a weekly calendar where we attach a recipe to a day and type of meal (lunch, dinner). We also have Week templates to save and reuse weekly plans.
- Todo: a todo list for the house tasks. We can export the meals of a week to a shopping list, and also create recurring tasks.

## Features
**Recipes**
- Recipe list grouped by category, with search and a category filter.
- Recipe detail with the photo, servings and the list of ingredients.
- Ingredients are free text in the recipe form, with suggestions of the existing ones. New ingredients are created on save.
- Photos are optional. They are resized to 1200px and stored as JPEG on upload, so the list stays light on the phone.
- Recipes or ingredients without a category go to `otros`. This category can't be deleted and it's always shown last.

**Planner**
- One week at a time, with arrows to move between weeks. On mobile the week header is sticky and highlights the day you are looking at.
- Add, replace or remove the lunch and dinner of each day.
- Servings: there is a household default ("Cooking for 2") and each meal can have its own number of servings.
- Each week can import a template, be saved as a new template or update an existing one.
- Export the shopping list of a week: you can preview the list, untick what you already have, change the name and add a due date before adding it to the todos. The quantities are scaled to the servings of each meal and summed per unit (`tomato: 1 ud + 300 g`).

**Templates**
- Reusable Mon–Sun plans. You can preview them from the list and edit the meals, name and description from the template page.

**Todos**
- Todos with subtasks, grouped by due date (Overdue, This week, Later, No date).
- Ticking a todo marks all its subtasks as done. Done todos are hidden from the list but you can find them in "Show done".
- Recurring todos (every N days/weeks/months/years). Only the next occurrence exists, and it's created when you tick the current one. The due date follows the schedule, so a Monday task stays on Mondays and missed occurrences are skipped.

**Home**
- Today's meals and the overdue and this week todos.

## Introduction
This codebase started from the template repo I use for my Django app developments. Including basic features and configurations ready to go
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

On top of that, this app adds:
- HTMX for the interactive parts (calendar slots, todos, dialogs). No frontend framework or build step.
- The whole site requires login (`LoginRequiredMiddleware`). There is no sign up page, the accounts are created by the admin (see below).
- A small design system in plain CSS. All the colors, fonts and sizes are CSS variables at the top of `static/css/base.css`, and each app has its own stylesheet using them. Icons are SVG files in `templates/icons/`.
- Mobile first. The phone is the main device, so on small screens there is a bottom tab bar and the planner, recipes and todos have their own layouts.

## Local development
To run the Django server, first copy the `.example.env` and rename it to `.env`. And then change the values on your interest. The `SECRET_KEY` can be generated with `python3 -c "import secrets; print(secrets.token_urlsafe())"`

Then you can proceed with the `docker compose up --build` to run the server inside a docker container that will serve the app in the port 8000 locally

Since there is no sign up, you need to create your user from the terminal:
```
docker compose run --rm django-app python manage.py createsuperuser
```
The rest of the household accounts can be created from the admin (`/admin/` → Users). They don't need to be superusers.

To collect the staticfiles you can use the `uv run manage.py collectstatic`. Run it also before the tests, otherwise the pages fail with `Missing staticfiles manifest entry`.

You can run formatter, linter, type checker and tests with:
```
uv run ruff format
uv run ruff check
uv run ty check
uv run manage.py test
```

The CI runs the same checks, and `ty` must pass with no errors. `ty` uses `django-stubs` for the Django types, but it doesn't run its mypy plugin, so the attributes Django adds at runtime (reverse relations like `todo.subtasks`, `recipe_id` fields, `get_FOO_display()`) are declared in the models inside an `if TYPE_CHECKING:` block. If you add a new one, declare it there too.

## Deployment
The `release.yml` workflow will build and push the docker image to Github container registry. From where you can later consume it. You can then create a production compose file with something like this:

```yaml
services:
  django-app:
    image: ghcr.io/jorgelg3/mealplanner:latest
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

You will then need to copy the [Nginx config file](nginx.conf) into the root folder from where you are serving the docker compose file. It already allows uploads up to 20MB for the recipe photos.

And finally create a `.env` file next to your compose file to provide the environment variables (`SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) — see [`.example.env`](.example.env) for reference.

Keep in mind that nginx serves the `/media/` files directly, so the recipe photos don't go through the login. The file names are not guessable, which is fine for recipe photos, but don't upload anything private there.

The migrations run when the container starts. A fresh database gets a default list of recipe and ingredient categories. An existing database keeps its own categories and only gets the `otros` fallback category.
