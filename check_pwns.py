from collections import OrderedDict

from lumberjack.lumberjack import Lumberjack
from utils.utils import read_settings_file, HTBhelper
from SQLWizard.sqlwizard import SQLWizard
from PWNgress import PWNgress


def check_pwns(db_filename, htb_api, discord_token, channel_id):
    log = Lumberjack("log/check_pwns_events.log", True)

    db = SQLWizard(db_filename)

    htb_helper = HTBhelper("", "", htb_api)

    log.info("Getting new PWNs")
    users, roots = htb_helper.get_pwns()

    log.info("Got users: " + str(users))
    log.info("Got roots: " + str(roots))

    notification_list = []

    # TODO: Change this
    for user_pwn in users:
        username = user_pwn[0].strip().lower()
        box_name = user_pwn[1].strip().lower()

        found_user = db.select("*", "names", "htb_name = '{}'".format(username))

        if not found_user:
            log.warning("User {} was not found in the database".format(username))
            continue

        found_box = db.select("*", "boxes", "name = '{}'".format(box_name))

        if not found_box:
            log.warning("Box {} was not found in the database".format(username))
            continue

        # check if already in root
        if username in found_box[0][6]:
            log.warning("User {} has got root {}".format(username, box_name))
            continue

        # check if already in user
        if username in found_box[0][5]:
            log.warning("User {} has got user {}".format(username, box_name))
            continue

        if found_box[0][3]:
            wts = found_box[0][3].replace(username + ",", "").replace(username, "")
        else:
            wts = "-"
        if found_box[0][4]:
            working = found_box[0][4].replace(username + ",", "").replace(username, "")
        else:
            working = "-"
        if found_box[0][5]:
            user = found_box[0][5].replace(username + ",", "").replace(username, "")
        else:
            user = "-"
        if found_box[0][6]:
            root = found_box[0][6].replace(username + ",", "").replace(username, "")
        else:
            root = "-"

        new_data = {}
        new_data["wts"] = wts if wts else "-"
        new_data["working"] = working if working else "-"
        new_data["user"] = user if user else "-"
        new_data["root"] = root if root else "-"

        if new_data["user"] and new_data["user"] != "-":
            new_data["user"] += "," + username
        else:
            new_data["user"] = username

        db.update(
            "boxes",
            OrderedDict([
                ("wts", new_data["wts"]),
                ("working", new_data["working"]),
                ("user", new_data["user"]),
                ("root", new_data["root"])
            ]),
            "name = '{}'".format(box_name)
        )

        log.info("Parsed {} on {} ({})".format("user", box_name, username))
        notification_list.append([username, "user", box_name])


    for root_pwn in roots:
        username = root_pwn[0].strip().lower()
        box_name = root_pwn[1].strip().lower()

        found_user = db.select("*", "names", "htb_name = '{}'".format(username))

        if not found_user:
            log.warning("User {} was not found in the database".format(username))
            continue

        found_box = db.select("*", "boxes", "name = '{}'".format(box_name))

        if not found_box:
            log.warning("Box {} was not found in the database".format(username))
            continue

        # check if already in root
        if username in found_box[0][6]:
            log.warning("User {} has got root {}".format(username, box_name))
            continue

        if found_box[0][3]:
            wts = found_box[0][3].replace(username + ",", "").replace(username, "")
        else:
            wts = "-"
        if found_box[0][4]:
            working = found_box[0][4].replace(username + ",", "").replace(username, "")
        else:
            working = "-"
        if found_box[0][5]:
            user = found_box[0][5].replace(username + ",", "").replace(username, "")
        else:
            user = "-"
        if found_box[0][6]:
            root = found_box[0][6].replace(username + ",", "").replace(username, "")
        else:
            root = "-"

        new_data = {}
        new_data["wts"] = wts if wts else "-"
        new_data["working"] = working if working else "-"
        new_data["user"] = user if user else "-"
        new_data["root"] = root if root else "-"

        if new_data["root"] and new_data["root"] != "-":
            new_data["root"] += "," + username
        else:
            new_data["root"] = username

        db.update(
            "boxes",
            OrderedDict([
                ("wts", new_data["wts"]),
                ("working", new_data["working"]),
                ("user", new_data["user"]),
                ("root", new_data["root"])
            ]),
            "name = '{}'".format(box_name)
        )

        log.info("Parsed {} on {} ({})".format("root", box_name, username))
        notification_list.append([username, "root", box_name])


    if notification_list:
        tmp_notification_list = [[channel_id] + x for x in notification_list]
        PWNgress(discord_token, db_filename, tmp_notification_list)


def main():
    settings_data = read_settings_file("settings.cfg")
    check_pwns(
        settings_data["DB_FILENAME"],
        settings_data["HTB_API"],
        settings_data["TOKEN"],
        settings_data["CHANNEL_ID"]
    )


if __name__ == '__main__':
    main()
