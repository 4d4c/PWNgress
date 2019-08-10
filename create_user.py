import sys
from collections import OrderedDict

from utils.utils import read_settings_file, HTBhelper
from SQLWizard.sqlwizard import SQLWizard


def update_record(db, own_type, box_name, username):
    box_data = db.select(own_type, "boxes", "name = '{}'".format(box_name.strip().lower()))
    if box_data[0][0]:
        new_data = box_data[0][0] + "," + username.strip().lower()
    else:
        new_data = username.strip().lower()

    db.update(
        "boxes",
        OrderedDict([
            (own_type, new_data)
        ]),
        "name = '{}'".format(box_name.strip().lower())
    )


def create_user(discord_id, url, discord_name, db_filename, htb_username, htb_password):
    db = SQLWizard(db_filename)

    user = db.select("*", "names", "discord_name = '{}'".format(discord_name))

    if user:
        print("ERROR: User exists")
        sys.exit(1)

    if not url.startswith("https://"):
        url = "https://www.hackthebox.eu/home/users/profile/" + url


    htb_helper = HTBhelper(htb_username, htb_password)

    if not htb_helper.login():
        print("ERROR: Failed to login")
        sys.exit(1)

    username, users, roots = htb_helper.get_user_info(url)

    print("Found username: " + username)
    print("Found users: " + ", ".join([x for x in users]))
    print("Found roots: " + ", ".join([x for x in roots]))

    db.insert(
        "names",
        OrderedDict([
            ("id", discord_id),
            ("htb_name", username),
            ("discord_name", discord_name)
        ])
    )

    for user in users:
        if user in roots:
            continue
        update_record(db, "user", user, username)

    for root in roots:
        update_record(db, "root", root, username)


def main():
    if len(sys.argv) != 4:
        print("ERROR: Usage python3 {} <DISCORD_ID> <HTB_URL/ID> <DISCORD_NAME>".format(sys.argv[0]))
        sys.exit(1)

    settings_data = read_settings_file("settings.cfg")
    create_user(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        settings_data["DB_FILENAME"],
        settings_data["HTB_USERNAME"],
        settings_data["HTB_PASSWORD"]
    )


if __name__ == '__main__':
    main()
