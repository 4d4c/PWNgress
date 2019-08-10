from collections import OrderedDict

from utils.utils import read_settings_file
from sqlwizard.sqlwizard import SQLWizard


def create_db(db_filename):
    """
    Create database structure.
    """

    db = SQLWizard(db_filename)

    db.create_table(
        "names",
        OrderedDict([
            ("id", "text"),
            ("htb_name", "text"),
            ("discord_name", "text")
        ])
    )

    db.create_table(
        "boxes",
        OrderedDict([
            ("name", "text"),
            ("score", "text"),
            ("image", "text"),
            ("wts", "text"),
            ("working", "text"),
            ("user", "text"),
            ("root", "text")
        ])
    )

    db.create_table(
        "status_update",
        OrderedDict([
            ("id", "text"),
            ("status", "text")
        ])
    )


def main():
    settings_data = read_settings_file("settings.cfg")
    create_db(settings_data["DB_FILENAME"])


if __name__ == '__main__':
    main()
