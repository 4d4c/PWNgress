from collections import OrderedDict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import json
import os
import requests
import textwrap
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
        # TODO: Add README
        # TODO: Rotate keys
        # TODO: better logging messages
        # TODO: move testing data to somewhere else
        # TODO: clean up image folder
        self.log = Lumberjack("../logs/PWNgress_events.log", True)

        self.db = SQLWizard("../database/PWNgress.sqlite")

        self.log.info("PWNgress started")

        self.htb_app_token = htb_app_token
        self.htb_team_id = htb_team_id
        self.discord_webhook_url = discord_webhook_url

        # Run the script every minute
        # TODO: Change how often we are running depending on the time
        self.loop(60)

    def loop(self, delay):
        """
        Core part of the script. Currently, only tracking team activities is implemented.
        """

        while True:
            self.get_and_save_team_members()
            # TODO: right now we will post it in order of the members, not in order of solves
            self.check_each_team_member_solves()

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

            # TODO: update the information
            self.log.debug("Adding new team member {}".format(member_data["id"]))

            self.db.insert(
                "htb_team_members",
                OrderedDict([
                    ("id", member_data["id"]),
                    ("htb_name", member_data["name"]),
                    ("discord_name", ""),  # Leave discord name empty
                    ("htb_avatar", "https://www.hackthebox.com" + member_data["avatar"]),
                    ("last_flag_date", ""),  # Leave last flag empty as we don't know it yet
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
        found_member_rows = self.db.select("id, htb_name, last_flag_date", "htb_team_members")
        for found_member_row in found_member_rows:
            member_id = found_member_row[0]
            member_name = found_member_row[1]
            member_last_flag_date = found_member_row[2]
            self.log.info("Checking {} ({}) solves".format(member_name, member_id))

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
                    self.send_message(member_id, member_name, activity_data)

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

    def create_image(self, htb_name, htb_user_avatar_url, htb_flag_type, message):
        """
        Create notification image. The image will consist of HTB user avatar, frame layers over the avatar,
        message describing flag obtained and image of the Flag.
        htb_flag_type - parameters is URL of the machine or type of the challenge.
        """

        # TODO: Move font names to settings file?
        # Size of notification image
        width = 500
        height = 110
        avatar_size = 80
        flag_size = 80
        margin_size = 15

        # Final image filename
        notification_filename = "/tmp/PWN.png"

        # Colors used in the notification
        background_color = (43, 45, 49)
        white_color = (255, 255, 255)
        red_color = (255, 0, 0)
        green_color = (0, 255, 0)
        endgame_color = (0, 134, 255)
        fortress_color = (148, 0, 255)
        challenge_color = (159, 239, 0)

        # HTTP headers for image downloading
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                          "Gecko/20100101 Firefox/111.0"
        }

        # Create main surface for the notification
        background_layer = Image.new(mode="RGB", size=(width, height), color=background_color)

        # Download HTB user image
        try:
            req = requests.get(htb_user_avatar_url, headers=headers)
        except Exception as err:
            self.log.error("Failed to get member image " + str(err))
            return False

        # Create Discord image
        discord_image = Image.open(io.BytesIO(req.content))
        discord_image.thumbnail((avatar_size, avatar_size))
        background_layer.paste(discord_image, (margin_size, margin_size))

        # Create flag/machine image
        if "hackthebox" in htb_flag_type:
            # If it's a machine flag we are passing URL and we need to download the image
            try:
                req = requests.get(htb_flag_type, headers=headers)
                machine_img = Image.open(io.BytesIO(req.content))
            except Exception as err:
                self.log.error("Failed to get machine image " + str(err))
                return False
        else:
            # If it's challenge, endgame or fortress flag we use local image
            machine_img = Image.open("../images/{}.png".format(htb_flag_type.lower()))

        new_machine_img = Image.new("RGBA", machine_img.size, background_color)
        new_machine_img.paste(machine_img, (0, 0), machine_img)
        new_machine_img.thumbnail((flag_size, flag_size))
        background_layer.paste(new_machine_img, (width - flag_size - margin_size, margin_size), new_machine_img)

        # Frame image
        frame_img = Image.open('../images/avatar_frame.png').convert("RGBA")
        img_thumb = frame_img.copy()
        img = img_thumb.resize((height, height))
        background_layer.paste(img, (0, 0), img)

        # Message text
        image_editable = ImageDraw.Draw(background_layer)
        image_editable.fontmode = "L"

        # If username is too big, we decrease the font size until it fits between avatar and flag images
        font_htb_name_size = 32
        while True:
            font_htb_name = ImageFont.truetype("../images/NoizeSport.ttf", size=font_htb_name_size, layout_engine=0)
            if font_htb_name.getsize(htb_name)[0] < 300:
                x_pos = width // 2 - font_htb_name.getsize(htb_name)[0] // 2 + 5
                image_editable.text((x_pos, margin_size), htb_name, fill=white_color, font=font_htb_name)
                break
            else:
                font_htb_name_size -= 1

        font_message = ImageFont.truetype("../images/Fixedsys.ttf", size=18, layout_engine=0)
        if message[1] == "ROOT " or message[1] == "USER ":
            # Machine message
            x_pos_1 = width // 2 - font_message.getsize("".join(message))[0] // 2 + 5
            x_pos_2 = x_pos_1 + font_message.getsize(message[0])[0]
            x_pos_3 = x_pos_2 + font_message.getsize(message[1])[0]

            image_editable.text((x_pos_1, 70), message[0], fill=white_color, font=font_message)
            if message[1] == "ROOT ":
                image_editable.text((x_pos_2, 70), message[1], fill=red_color, font=font_message)
            else:
                image_editable.text((x_pos_2, 70), message[1], fill=green_color, font=font_message)
            image_editable.text((x_pos_3, 70), message[2], fill=white_color, font=font_message)
        else:
            # Challenge, endgame or fortress message
            x_pos_1 = width // 2 - font_message.getsize("".join([message[0], message[1]]))[0] // 2 + 5
            x_pos_2 = x_pos_1 + font_message.getsize("".join(message[0]))[0]
            x_pos_3 = width // 2 - font_message.getsize(message[2])[0] // 2 + 5

            # Shorten name of the long flags
            if len(message[0]) > 30:
                message = message[0][:25] + "..."
            image_editable.text((x_pos_1, 65), message[0], fill=white_color, font=font_message)
            if "endgame" in message[2]:
                image_editable.text((x_pos_2, 65), message[1], fill=endgame_color, font=font_message)
            elif "fortress" in message[2]:
                image_editable.text((x_pos_2, 65), message[1], fill=fortress_color, font=font_message)
            elif "challenge" in message[2]:
                image_editable.text((x_pos_2, 65), message[1], fill=challenge_color, font=font_message)
            image_editable.text((x_pos_3, 80), message[2], fill=white_color, font=font_message)

        # background_layer.show()

        # Save image as a file and return
        background_layer.save(notification_filename)

        return notification_filename

    def send_message(self, member_id, htb_name, activity_data):
        """
        Send message in Discord using Webhook.
        """

        self.log.info("Send message")

        htb_user_avatar_url = self.db.select("htb_avatar", "htb_team_members", f"id = '{member_id}'")[0][0]

        # Create different messages for different type of solves and assign flag type (machine/challenge)
        message = ""
        htb_flag_type = ""
        if activity_data["object_type"] == "machine":
            message = [
                "Owned ",
                activity_data["type"].upper() + " ",
                activity_data["name"] + " " + activity_data["object_type"]
            ]
            htb_flag_type = "https://www.hackthebox.com" + activity_data["machine_avatar"].replace("_thumb", "")
        elif activity_data["object_type"] == "challenge":
            message = [
                "Owned ",
                activity_data["name"],
                activity_data["challenge_category"] + " " + activity_data["object_type"]
            ]
            htb_flag_type = activity_data["challenge_category"]
        elif activity_data["object_type"] == "fortress":
            message = [
                "Owned ",
                activity_data["flag_title"],
                # Shorten name for Context fortress
                activity_data["name"].replace("Cyber Attack Simulation", "") + " " + activity_data["object_type"]
            ]
            htb_flag_type = activity_data["object_type"]
        elif activity_data["object_type"] == "endgame":
            message = [
                "Owned ",
                activity_data["flag_title"],
                activity_data["name"] + " " + activity_data["object_type"]
            ]
            htb_flag_type = activity_data["object_type"]

        # Create notification image
        notification_filename = self.create_image(htb_name, htb_user_avatar_url, htb_flag_type, message)

        # Send image to Discord
        if notification_filename:
            image_file = {
                "PWN": open(notification_filename, "rb")
            }

            try:
                r = requests.post(self.discord_webhook_url, files=image_file)
            except Exception as err:
                self.log.error("Failed to send Discord message")
                self.log.error(traceback.print_exc())


def main():
    settings = read_settings_file("settings/PWNgress_settings.cfg")
    PWNgress(settings["HTB_APP_TOKEN"], settings["HTB_TEAM_ID"], settings["DISCORD_WEBHOOK_URL"])


if __name__ == "__main__":
    main()
