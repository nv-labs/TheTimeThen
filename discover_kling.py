import fal
import os

fal.api_key = os.environ.get("FAL_KEY")

apps = fal.apps.list()

for app in apps:
    if "kling" in app["name"].lower():
        print(app["name"])
