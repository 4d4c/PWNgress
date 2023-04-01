from collections import OrderedDict
from datetime import datetime
import json
import os
import requests
import time
import traceback

from lumberjack.lumberjack import Lumberjack
from utils.utils import read_settings_file, create_sha256_hash
from SQLWizard.sqlwizard import SQLWizard


class PWNgress():
    """
    PWNgress.
    """

    def __init__(self, htb_app_token, htb_team_id, discord_webhook_url):
        self.log = Lumberjack("logs/PWNgress_events.log", True)

        self.db = SQLWizard("database/PWNgress.sqlite")

        self.log.info("PWNgress started")

        self.htb_app_token = htb_app_token
        self.htb_team_id = htb_team_id
        self.discord_webhook_url = discord_webhook_url

        # This hash will be used to prevent sending multiple messages on the same
        # member activity event (user submitted flag)
        # self.last_flag_hash_filename = "logs/PWNgress_last_flag_hash.log"
        # self.get_last_flag_hash()

        # Run the script every minute
        self.loop(60)

    def get_last_flag_hash(self):
        """
        Read SHA256 hash of the last activity from `self.last_flag_hash_filename` file.
        If file doesn't exist it means that we are running the script for the first time.
        """

        # TODO: remove
        self.log.info("Getting last flag hash")

        if not os.path.exists(self.last_flag_hash_filename):
            self.last_flag_hash = ""
            self.log.warning("Last flag hash was not set")
        else:
            with open(self.last_flag_hash_filename, "r") as in_file:
                self.last_flag_hash = in_file.readline().strip()
                self.log.debug("Got last flag hash: " + self.last_flag_hash)

    def set_last_flag_hash(self):
        """
        Write SHA256 hash of the last activity to `self.last_flag_hash_filename` file.
        """

        # TODO: remove
        self.log.info("Saving last flag hash: " + self.last_flag_hash)

        with open(self.last_flag_hash_filename, "w") as in_file:
            in_file.write(self.last_flag_hash)

    def loop(self, delay):
        """
        Core part of the script. Currently, only tracking team activities is implemented.
        """

        while True:
            self.get_and_save_team_members()
            self.check_each_team_member_solves()
            # self.get_team_activities()
            # with open("test_data.json", "r") as f:
            #     self.process_team_activities(json.load(f))

            time.sleep(delay)

    def get_and_save_team_members(self):
        """
        Get all team members and save them to the local database.
        """

        self.log.info("Getting team members")

        try:
            team_members_link = "https://www.hackthebox.com" \
                                    "/api/v4/team/members/{}".format(self.htb_team_id)

            headers = {
                "Authorization": "Bearer " + self.htb_app_token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                              "Gecko/20100101 Firefox/111.0"
            }

            r = requests.get(team_members_link, headers=headers)
            team_members_json_data = json.loads(r.text)
        except Exception as err:
            self.log.error("Failed to get team members " + str(err))

        # with open("test_team_members.json", "r") as f:
        #     team_members_json_data = json.load(f)

        for member_data in team_members_json_data:
            # Check if the team member is already in the database
            if self.db.select("id", "htb_team_members", "id = '{}'".format(member_data["id"])):
                self.log.debug("Team member {} already in the database".format(member_data["id"]))
                continue

            self.log.debug("Adding new team member {}".format(member_data["id"]))

            self.db.insert(
                "htb_team_members",
                OrderedDict([
                    ("id", member_data["id"]),
                    ("name", member_data["name"]),
                    ("last_flag_date", ""),  # Leaving last flag empty as we don't know it yet
                    ("points", member_data["points"]),
                    ("rank", member_data["rank"]),
                    ("json_data", json.dumps(member_data))
                ])
            )

    def check_each_team_member_solves(self):
        """
        Check solves of each team member.
        """

        self.log.info("Checking team members solves")

        # Get all team members from the database
        found_member_rows = self.db.select("id, name, last_flag_date", "htb_team_members")
        for found_member_row in found_member_rows:
            member_id = found_member_row[0]
            member_name = found_member_row[1]
            member_last_flag_date = found_member_row[2]

            member_solves_json = self.get_user_activities(member_id)
            # with open("test_member_activity_{}.json".format(member_id), "r") as f:
            #     member_solves_json = json.load(f)

            if member_solves_json == "":
                continue

            if len(member_solves_json["profile"]["activity"]) == 0:
                continue

            # If member is new and we didn't record the last flag yet, don't go through each
            # activity and just save the last one
            if member_last_flag_date == "":
                self.db.update(
                    "htb_team_members",
                    OrderedDict([
                        ("last_flag_date", member_solves_json["profile"]["activity"][0]["date"])
                    ]),
                    "id = '{}'".format(member_id)
                )
                continue

            # Reverse the order of the JSON we received from HTB. This will allow us to
            # to create notification in order in which the flags were obtained
            for activity_data in reversed(member_solves_json["profile"]["activity"]):
                # Compare dates and send flag if newer
                date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
                last_flag_date_from_db = datetime.strptime(member_last_flag_date, date_format)
                last_flag_date_from_api = datetime.strptime(activity_data["date"], date_format)

                if last_flag_date_from_api > last_flag_date_from_db:
                    self.send_message(member_name, activity_data)

            self.db.update(
                "htb_team_members",
                OrderedDict([
                    ("last_flag_date", activity_data["date"])
                ]),
                "id = '{}'".format(member_id)
            )

    def get_user_activities(self, user_id):
        """
        Get user activities.
        """

        self.log.info("Checking user activities")
        try:
            team_activity_link = "https://www.hackthebox.com" \
                                 "/api/v4/user/profile/activity/{}".format(user_id)

            headers = {
                "Authorization": "Bearer " + self.htb_app_token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                              "Gecko/20100101 Firefox/111.0"
            }

            r = requests.get(team_activity_link, headers=headers)
            user_activities = json.loads(r.text)

            self.log.debug("Found {} activities".format(len(user_activities["profile"]["activity"])))

            return user_activities
        except Exception as err:
            self.log.error("Failed to get member activities " + str(err))
            return ""

    def get_team_activities(self):
        """
        Use HTB API to obtain all member activities. Because HTB team activiites are delayed
        by ~30 min, we don't use this method.
        """

        self.log.info("Getting team activities")

        try:
            team_activity_link = "https://www.hackthebox.com" \
                                 "/api/v4/team/activity/{}?n_past_days=1".format(self.htb_team_id)

            headers = {
                "Authorization": "Bearer " + self.htb_app_token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                              "Gecko/20100101 Firefox/111.0"
            }

            r = requests.get(team_activity_link, headers=headers)
            team_activity_json_data = json.loads(r.text)

            self.process_team_activities(team_activity_json_data)

            self.log.debug("Found {} activities".format(len(team_activity_json_data)))
        except Exception as err:
            self.log.error("Failed to get team activities " + str(err))

    def process_team_activities(self, team_activity_json_data):
        """
        For each new activity send notification
        """

        self.log.info("Processing team activities")

        # Flag to track if we found new activity (someone got a new flag)
        new_flag = False

        # If it's the first time the script is executed and the last flag hash is not set,
        # get last activity hash and save it.
        if self.last_flag_hash == "":
            self.log.warning("Empty flag hash")

            # Hash is created from date when flag was obtained and HTB member ID
            activity_hash_str = "{}-{}".format(team_activity_json_data[0]["date"],
                                               str(team_activity_json_data[0]["user"]["id"]))
            self.last_flag_hash = create_sha256_hash(activity_hash_str)
            # Save last activity hash in file
            self.set_last_flag_hash()

            return

        # Reverse the order of the JSON we received from HTB. This will allow us to
        # to create notification in order in which the flags were obtained.
        for activity_data in reversed(team_activity_json_data):
            # Hash is created from date when flag was obtained and HTB member ID
            activity_hash_str = activity_data["date"] + "-" + str(activity_data["user"]["id"])
            activity_hash = create_sha256_hash(activity_hash_str)

            self.log.debug("Processing team activity: " + activity_hash)

            # If we found activity that we notified the last we skip it and set the `new_flag`
            if self.last_flag_hash == activity_hash:
                self.log.info("Found new team activity")
                new_flag = True
                continue

            # If we found new activity, we send the notification to Discord handler
            if new_flag:
                self.last_flag_hash = activity_hash

                self.log.debug("New activity data: " + activity_hash_str)
                self.log.debug("New activity hash: " + activity_hash)

                # Send message in the discord
                self.send_message(activity_data)

                # Save last activity hash in file
                self.set_last_flag_hash()

                # TODO: Added this for testing to prevent sending large number of messages
                # in short amount of time
                time.sleep(5)

    def send_message(self, member_name, activity_data):
        """
        Send message in Discord using Webhook.
        Currently implemented using embed element.
        """

        self.log.info("Send message")

        try:
            headers = {
                "Content-type": "application/json"
            }

            # Placeholder for message thumbnails. HTB stores challenges and fortress images in SVG
            # format that is not supported by Discord API.
            # We can adjust all this code to whatever message design we want
            if activity_data["object_type"] == "challenge":
                thumbnail_url = "https://pbs.twimg.com"\
                                "/profile_images/1610589411682418690/GBT-ZJlC_400x400.jpg"
            elif activity_data["object_type"] == "fortress":
                thumbnail_url = "https://pbs.twimg.com"\
                                "/profile_images/1610589411682418690/GBT-ZJlC_400x400.jpg"
            elif activity_data["object_type"] == "machine":
                thumbnail_url = "https://www.hackthebox.com" + activity_data["machine_avatar"]

            # Craft specific message descriptions for each type of flag
            if activity_data["object_type"] == "challenge":
                description = "Owned **{}** {} {}".format(activity_data["name"],
                                                          activity_data["challenge_category"].lower(),
                                                          activity_data["object_type"])
            elif activity_data["object_type"] == "fortress":
                description = "Owned **{}** flag in {} {}".format(activity_data["flag_title"],
                                                                  activity_data["name"],
                                                                  activity_data["object_type"])
            elif activity_data["object_type"] == "machine":
                description = "Owned **{}** on {} {}".format(activity_data["type"],
                                                             activity_data["name"],
                                                             activity_data["object_type"])

            # Create Discord embed element
            embed_json = {
                "content": "",
                "embeds": [
                    {
                        "type": "rich",
                        "title": member_name.upper(),
                        "description": description,
                        "timestamp": activity_data["date"],
                        # TODO: add blue colour for challenges and purple for fortress
                        "color": "16711680" if activity_data["type"] == "root" else "2293504",
                        "thumbnail": {
                            "url": thumbnail_url
                        }
                    }
                ]
            }

            r = requests.post(self.discord_webhook_url, headers=headers, json=embed_json)
        except Exception as err:
            self.log.error("Failed to send Discord message")
            self.log.error(traceback.print_exc())


def main():
    settings = read_settings_file("settings/PWNgress_settings.cfg")
    PWNgress(settings["HTB_APP_TOKEN"], settings["HTB_TEAM_ID"], settings["DISCORD_WEBHOOK_URL"])


if __name__ == '__main__':
    main()
