import sys
import json
from collections import OrderedDict

from utils.utils import read_settings_file, HTBhelper
from sqlwizard.sqlwizard import SQLWizard


def update_machines(db_filename, htb_username, htb_password, htb_api):
    db = SQLWizard(db_filename)

    htb_helper = HTBhelper(htb_username, htb_password, htb_api)

    if not htb_helper.login():
        print("ERROR: Failed to login")
        sys.exit(1)

    all_machines_json = htb_helper.get_all_machines()

    if not all_machines_json:
        print("ERROR: Failed to get machines JSON")

    all_machines_json = json.loads(all_machines_json)

    for machine in all_machines_json:
        if db.select("name", "boxes", "name = '{}'".format(machine["name"].strip().lower())):
            continue

        machine_image = machine["avatar_thumb"].replace("_thumb", "")
        machine_id = machine["id"]
        machine_score = htb_helper.get_machine_score(machine_id)

        db.insert(
            "boxes",
            OrderedDict([
                ("name", machine["name"].strip().lower()),
                ("score", machine_score),
                ("image", machine_image),
                ("wts", "-"),
                ("working", "-"),
                ("user", "-"),
                ("root", "-")
            ])
        )


def main():
    settings_data = read_settings_file("settings.cfg")
    update_machines(
        settings_data["DB_FILENAME"],
        settings_data["HTB_USERNAME"],
        settings_data["HTB_PASSWORD"],
        settings_data["HTB_API"],
    )


if __name__ == '__main__':
    main()
