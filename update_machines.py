import sys
import json
from collections import OrderedDict

from lumberjack.lumberjack import Lumberjack
from utils.utils import read_settings_file, HTBhelper
from SQLWizard.sqlwizard import SQLWizard


def update_machines(db_filename, htb_username, htb_password, htb_api):
    log = Lumberjack("log/update_machines_events.log", True)

    db = SQLWizard(db_filename)

    htb_helper = HTBhelper(htb_username, htb_password, htb_api)

    if not htb_helper.login():
        log.error("ERROR: Failed to login")
        sys.exit(1)

    log.info("Getting all machines")
    all_machines_json = htb_helper.get_all_machines()

    if not all_machines_json:
        log.error("ERROR: Failed to get machines json")
        sys.exit(1)

    all_machines_json = json.loads(all_machines_json)

    for box in all_machines_json:
        box_name = box["name"].strip().lower()
        if db.select("name", "boxes", "name = '{}'".format(box_name)):
            log.debug("Box {} already in the database".format(box_name))
            continue

        box_image = box["avatar_thumb"].replace("_thumb", "")
        box_id = box["id"]

        log.info("Getting {} ({}) box score".format(box_name, box_id))
        box_score = htb_helper.get_machine_score(box_id)

        log.info("Adding new box {} {}".format(box_name, box_score))
        db.insert(
            "boxes",
            OrderedDict([
                ("name", box_name),
                ("score", box_score),
                ("image", box_image),
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
