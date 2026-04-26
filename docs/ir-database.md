# IR Database

![IR Database walkthrough: search, browse, import](/gifs/irdb.gif)

IR2MQTT includes a comprehensive database of IR codes sourced from the **Flipper Zero** and **Probono** communities. You can use this to find codes for your devices without needing a physical remote.

:::tip One-time download required
The database files are not bundled with IR2MQTT to keep the image size small. Go to **IR Database → Download** in the UI to fetch them. This only needs to be done once; the files are stored in `/data/ir_database/`.
:::

## Finding Codes

1. **Search** — Type the brand or model name (e.g. `Samsung TV`) into the search bar. Results appear from both databases simultaneously.
2. **Browse** — Navigate the folder tree: **Brand → Device Type → Model**. Useful when you don't know the exact model name.
3. **Test before importing** — Hover over any button in the browser and click the **send icon** to transmit the code immediately. Use this to confirm the code works with your device before adding it.

## Importing Codes

1. Find your device in the database.
2. Select the buttons you want (or use **Select All**).
3. Click **Import into Device** and choose the target device from the dropdown.

The imported buttons are added to the device without overwriting existing ones. Duplicate button names are automatically suffixed (e.g. `Power_1`).

## Database Sources

| Source | Coverage | Format |
|--------|----------|--------|
| Flipper Zero | 1000+ devices, broad brand coverage | `.ir` files |
| Probono | Deep coverage for AV equipment | Custom format |

:::warning Code compatibility
Database codes are community-contributed and may not work for every revision of a device. If a code doesn't work, try another entry for the same brand, or learn the code directly from your physical remote using **Learning Mode**.
:::

## Updating the Database

Re-run the download from the UI to fetch the latest community-updated files. Existing learned codes on your devices are never modified by a database update.
