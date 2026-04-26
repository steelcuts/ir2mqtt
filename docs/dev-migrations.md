# Database Migrations

IR2MQTT uses **Alembic** to handle changes to the database schema without losing user data.

## Workflow

1. **Modify Models:** Change the SQLAlchemy models in `backend/db/models.py`.
2. **Create Migration:** Run `make migration-create m="add new field to device"`. This generates a new Python script in `migrations/versions/`.
3. **Review:** Check the generated script to ensure it correctly reflects your changes.
4. **Apply Locally:** Run `make migrate` to update your local development database.

## Troubleshooting "New upgrade operations detected"
If `make migrate-check` fails with an error stating that new operations were detected (like `add_table`), it means your database schema is not in sync with your models.

- **If the tables already exist:** Run `make migrate-stamp` to mark the current state as updated.
- **If it is a fresh installation:** Run `make migrate` to actually create the tables.
- **If you changed models:** Run `make migration-create m="your message"` to generate the missing script.

## Automatic Updates
When running as a Docker container or Home Assistant Add-on, migrations are applied **automatically** on every startup. This ensures that the database schema is always compatible with the application code.