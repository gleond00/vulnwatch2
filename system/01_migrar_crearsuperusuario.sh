#!/bin/bash

# Hemos de hacer migraciones de algunas apps a mano porque si no da error creando las tablas.

cd /vulnwatch2
rm -f db.sqlite3
rm -r core/migrations
python3 manage.py makemigrations core
python3 manage.py makemigrations
python3 manage.py migrate auth
python3 manage.py migrate

python3 manage.py createsuperuser

# python3 ./puebla_db.py