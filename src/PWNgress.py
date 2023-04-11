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

    def __init__(self, htb_app_token, htb_team_id, discord_webhook_url, font_htb_name, font_message,
                 htb_users_to_ignore):
        self.log = Lumberjack("../logs/PWNgress_events.log", True)

        self.db = SQLWizard("../database/PWNgress.sqlite")

        self.log.info("PWNgress started")

        self.htb_app_token = htb_app_token
        self.htb_team_id = htb_team_id
        self.discord_webhook_url = discord_webhook_url
        self.font_htb_name = font_htb_name
        self.font_message = font_message
        self.htb_users_to_ignore = htb_users_to_ignore.split(",")

        self.message_queue = {}

        # Run the script every minute
        self.loop(60)

    def loop(self, delay):
        """
        Core part of the script. Currently, only tracking team activities is implemented.
        """

        check = []
        while True:
            # self.get_and_save_team_members()
            # self.check_each_team_member_solves()
            # self.send_member_solves_messages()

            self.log.debug(datetime.now().time().strftime("%H:%M"))

            if datetime.now().time().strftime("%H:%M") == '19:59' or\
                datetime.now().time().strftime("%H:%M") == '20:00' or\
                datetime.now().time().strftime("%H:%M") == '20:01':

                if "20" not in check:
                    self.get_and_save_team_members()
                    self.check_each_team_member_solves()
                    self.log.warning(datetime.now().time().strftime("%H:%M"))

                    self.get_team_ranking()
                    self.get_members_ranking()
                    self.send_ranking_message()
                    check.append("20")

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

            req = requests.get(team_members_link, headers=headers)
            team_members_json_data = json.loads(req.text)
        except Exception as err:
            self.log.error("Failed to get team members " + str(err))
            return

        # with open("test/test_team_members.json", "w") as f:
        #     json.dump(team_members_json_data, f)
        # with open("test/test_team_members.json", "r") as f:
        #     team_members_json_data = json.load(f)

        all_member_ids = [x[0] for x in self.db.select("id", "htb_team_members")]
        # TODO: remove inactive users
        for member_data in team_members_json_data:
            # Ignore inactive users
            if str(member_data["id"]) == self.htb_users_to_ignore:
                continue
            # Check if the team member is already in the database
            if member_data["id"] in all_member_ids:
                self.log.debug("Team member {} ({}) already in the database".format(
                    member_data["name"],
                    member_data["id"]
                ))
                self.db.update(
                    "htb_team_members",
                    OrderedDict([
                        ("htb_name", member_data["name"]),
                        ("htb_avatar", "https://www.hackthebox.com" + member_data["avatar"]),
                        ("points", member_data["points"]),
                        ("rank", member_data["rank"]),
                        ("json_data", json.dumps(member_data))
                    ]),
                    "id = '{}'".format(member_data["id"])
                )
            else:
                self.log.debug("Adding new team member {} ({})".format(
                    member_data["name"],
                    member_data["id"]
                ))
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

            member_solves_json = self.get_user_activities(member_name, member_id)
            # with open("test/test_member_activity_{}.json".format(member_id), "w") as f:
            #     json.dump(member_solves_json, f)
            # with open("test/test_member_activity_{}.json".format(member_id), "r") as f:
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

            # Check if new activity
            date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
            last_flag_date_from_db = datetime.strptime(member_last_flag_date, date_format)

            for activity_data in reversed(member_solves_json["profile"]["activity"]):
                last_flag_date_from_api = datetime.strptime(activity_data["date"], date_format)

                if last_flag_date_from_api > last_flag_date_from_db:
                    # Temporary store all messages that we will send. Later we will sort them.
                    # This will allow us to create notification in order in which the flags were obtained
                    self.message_queue["{}_{}".format(last_flag_date_from_api.timestamp(), member_id)] = {
                        "member_id": member_id,
                        "member_name": member_name,
                        "activity_data": activity_data
                    }

            self.db.update(
                "htb_team_members",
                OrderedDict([
                    ("last_flag_date", activity_data["date"])
                ]),
                "id = '{}'".format(member_id)
            )

    def get_user_activities(self, member_name, user_id):
        """
        Get user activities.
        """

        self.log.info("Checking user activities {} ({})".format(member_name, user_id))

        try:
            team_activity_link = "https://www.hackthebox.com" \
                                 "/api/v4/user/profile/activity/{}".format(user_id)

            headers = {
                "Authorization": "Bearer " + self.htb_app_token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                              "Gecko/20100101 Firefox/111.0"
            }

            req = requests.get(team_activity_link, headers=headers)
            user_activities = json.loads(req.text)

            # self.log.debug("Found {} activities".format(len(user_activities["profile"]["activity"])))

            return user_activities
        except Exception as err:
            self.log.error("Failed to get member activities " + str(err))
            return ""

    def get_team_ranking(self):
        """
        """

        self.log.info("Getting new team ranking")

        try:
            team_info_link = "https://www.hackthebox.com" \
                             "/api/v4/team/info/{}".format(self.htb_team_id)
            team_stats_link = "https://www.hackthebox.com" \
                              "/api/v4/team/stats/owns/{}".format(self.htb_team_id)

            headers = {
                "Authorization": "Bearer " + self.htb_app_token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                              "Gecko/20100101 Firefox/111.0"
            }

            req = requests.get(team_info_link, headers=headers)
            team_info_data = json.loads(req.text)

            req = requests.get(team_stats_link, headers=headers)
            team_stats_data = json.loads(req.text)
        except Exception as err:
            self.log.error("Failed to get team ranking data " + str(err))
            return

        rank_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.db.insert(
            "team_ranking",
            OrderedDict([
                ("rank_date", rank_date),
                ("rank", team_stats_data["rank"]),
                ("points", team_info_data["points"]),
                ("user_owns", team_stats_data["user_owns"]),
                ("system_owns", team_stats_data["system_owns"]),
                ("challenge_owns", team_stats_data["challenge_owns"]),
                ("respects", team_stats_data["respects"])
            ])
        )

    def get_members_ranking(self):
        """
        """

        self.log.info("Getting new team members ranking")

        # Get all team members from the database
        found_member_rows = self.db.select("id, htb_name, rank, points, last_flag_date", "htb_team_members")
        for found_member_row in found_member_rows:
            member_id = found_member_row[0]
            member_name = found_member_row[1]
            member_rank = found_member_row[2]
            member_points = found_member_row[3]
            member_last_flag_date = found_member_row[4]

            self.log.info("Getting member ranking data for user {} ({})".format(member_name, member_id))

            try:
                member_basic_link = "https://www.hackthebox.com" \
                                    "/api/v4/user/profile/basic/{}".format(member_id)
                member_challenges_link = "https://www.hackthebox.com" \
                                         "/api/v4/user/profile/progress/challenges/{}".format(member_id)
                member_fortress_link = "https://www.hackthebox.com" \
                                       "/api/v4/user/profile/progress/fortress/{}".format(member_id)
                member_endgame_link = "https://www.hackthebox.com" \
                                      "/api/v4/user/profile/progress/endgame/{}".format(member_id)
                member_prolab_link = "https://www.hackthebox.com" \
                                      "/api/v4/user/profile/progress/prolab/{}".format(member_id)
                headers = {
                    "Authorization": "Bearer " + self.htb_app_token,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                                "Gecko/20100101 Firefox/111.0"
                }

                req = requests.get(member_basic_link, headers=headers)
                member_basic_data = json.loads(req.text)

                req = requests.get(member_challenges_link, headers=headers)
                member_challenges_data = json.loads(req.text)

                req = requests.get(member_fortress_link, headers=headers)
                member_fortress_data = json.loads(req.text)

                req = requests.get(member_endgame_link, headers=headers)
                member_endgame_data = json.loads(req.text)

                req = requests.get(member_prolab_link, headers=headers)
                member_prolab_data = json.loads(req.text)

            except Exception as err:
                self.log.error("Failed to get team ranking data " + str(err))
                return

            fortress_count = 0
            for member_fortress in member_fortress_data["profile"]["fortresses"]:
                fortress_count += member_fortress["owned_flags"]

            endgame_count = 0
            for member_fortress in member_endgame_data["profile"]["endgames"]:
                endgame_count += member_fortress["owned_flags"]

            prolab_count = 0
            for member_fortress in member_prolab_data["profile"]["prolabs"]:
                prolab_count += member_fortress["owned_flags"]

            rank_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            self.db.insert(
                "member_ranking",
                OrderedDict([
                    ("id", member_id),
                    ("rank_date", rank_date),
                    ("htb_name", member_name),
                    ("rank", member_rank),
                    ("points", member_points),
                    ("user_owns", member_basic_data["profile"]["user_owns"]),
                    ("system_owns", member_basic_data["profile"]["system_owns"]),
                    ("challenge_owns", member_challenges_data["profile"]["challenge_owns"]["solved"]),
                    ("fortress_owns", fortress_count),
                    ("endgame_owns", endgame_count),
                    ("prolabs_owns", prolab_count),
                    ("user_bloods", member_basic_data["profile"]["user_bloods"]),
                    ("system_bloods", member_basic_data["profile"]["system_bloods"]),
                    ("last_flag_date", member_last_flag_date),
                    ("respects", member_basic_data["profile"]["respects"])
                ])
            )


    def send_ranking_message(self):
        """
        """

        self.log.info("Sending ranking message")

        # TODO: add order and limit to SQLWizard
        last_two_ranking_data = self.db.select(
            "*",
            "team_ranking",
            "rank > 0 ORDER BY rank_date DESC LIMIT 2"
        )

        diff_rank = last_two_ranking_data[0][1] - last_two_ranking_data[1][1]
        diff_points = last_two_ranking_data[0][2] - last_two_ranking_data[1][2]
        diff_user_owns = last_two_ranking_data[0][3] - last_two_ranking_data[1][3]
        diff_system_owns = last_two_ranking_data[0][4] - last_two_ranking_data[1][4]
        diff_challenge_owns = last_two_ranking_data[0][5] - last_two_ranking_data[1][5]
        diff_respects = last_two_ranking_data[0][6] - last_two_ranking_data[1][6]
        team_message = "```plaintext\n"
        team_message += "+-----------------------------------------------------------------------------------------------------+\n"
        team_message += "|                                            TEAM RANKING                                             |\n"
        team_message += "+----------------+----------------+----------------+----------------+----------------+----------------+\n"
        team_message += "|      RANK      |     POINTS     |   USERS OWNS   |   SYSTEM OWNS  | CHALLENGE OWNS |    RESPECTS    |\n"
        team_message += "+----------------+----------------+----------------+----------------+----------------+----------------+\n"

        team_message += "|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|\n".format(
            "{} ({})".format(last_two_ranking_data[0][1], diff_rank),
            "{} ({})".format(last_two_ranking_data[0][2], diff_points),
            "{} ({})".format(last_two_ranking_data[0][3], diff_user_owns),
            "{} ({})".format(last_two_ranking_data[0][4], diff_system_owns),
            "{} ({})".format(last_two_ranking_data[0][5], diff_challenge_owns),
            "{} ({})".format(last_two_ranking_data[0][6], diff_respects)
        )
        team_message += "+-----------------------------------------------------------------------------------------------------+\n"
        team_message += "```\n"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                          "Gecko/20100101 Firefox/111.0",
            "Content-Type": "application/json"
        }

        message_data = {
            "content": team_message
        }
        try:
            req = requests.post(self.discord_webhook_url, headers=headers, json=message_data)
        except Exception as err:
            self.log.error("Failed to send Discord message")
            self.log.error(traceback.print_exc())

        # member_message = "```plaintext\n"
        member_message = ""
        member_message += "+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+\n"
        member_message += "|                                                                                                    MEMBER RANKING                                                                                                   |\n"
        member_message += "+--------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+-----------+\n"
        member_message += "|     NAME     |      RANK      |     POINTS     |      USER      |     SYSTEM     |   CHALLENGES   |    FORTRESS    |     ENDGAME    |     PROLABS    |    U BLOODS    |    S BLOODS    |    RESPECTS    | LAST FLAG |\n"
        member_message += "+--------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+----------------+-----------+\n"
        # Get all team members from the database
        found_member_rows = self.db.select("id", "htb_team_members", "id > 0 ORDER by rank ASC")
        for found_member_row in found_member_rows:
            member_id = found_member_row[0]
            last_two_ranking_data = self.db.select(
                "*",
                "member_ranking",
                "id = {} ORDER BY rank_date DESC LIMIT 2".format(member_id)
            )

            diff_rank = last_two_ranking_data[0][3] - last_two_ranking_data[1][3]
            diff_points = last_two_ranking_data[0][4] - last_two_ranking_data[1][4]
            diff_user_owns = last_two_ranking_data[0][5] - last_two_ranking_data[1][5]
            diff_system_owns = last_two_ranking_data[0][6] - last_two_ranking_data[1][6]
            diff_challenge_owns = last_two_ranking_data[0][7] - last_two_ranking_data[1][7]
            diff_fortress_owns = last_two_ranking_data[0][8] - last_two_ranking_data[1][8]
            diff_endgame_owns = last_two_ranking_data[0][9] - last_two_ranking_data[1][9]
            diff_prolab_owns = last_two_ranking_data[0][10] - last_two_ranking_data[1][10]
            diff_user_bloods = last_two_ranking_data[0][11] - last_two_ranking_data[1][11]
            diff_system_bloods = last_two_ranking_data[0][12] - last_two_ranking_data[1][12]
            diff_respects = last_two_ranking_data[0][14] - last_two_ranking_data[1][14]

            member_message += "|{:14s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:11s}|\n".format(
                last_two_ranking_data[0][2],
                "{} ({})".format(last_two_ranking_data[0][3], diff_rank),
                "{} ({})".format(last_two_ranking_data[0][4], diff_points),
                "{} ({})".format(last_two_ranking_data[0][5], diff_user_owns),
                "{} ({})".format(last_two_ranking_data[0][6], diff_system_owns),
                "{} ({})".format(last_two_ranking_data[0][7], diff_challenge_owns),
                "{} ({})".format(last_two_ranking_data[0][8], diff_fortress_owns),
                "{} ({})".format(last_two_ranking_data[0][9], diff_endgame_owns),
                "{} ({})".format(last_two_ranking_data[0][10], diff_prolab_owns),
                "{} ({})".format(last_two_ranking_data[0][12], diff_user_bloods),
                "{} ({})".format(last_two_ranking_data[0][12], diff_system_bloods),
                "{} ({})".format(last_two_ranking_data[0][14], diff_respects),
                datetime.strftime(datetime.strptime(last_two_ranking_data[0][13], "%Y-%m-%dT%H:%M:%S.%fZ"), "%Y-%m-%d")
            )

        member_message += "+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+\n"

        message_filename = "/tmp/message.txt"
        with open(message_filename, "w") as out_file:
            out_file.write(member_message)
        image_file = {
            "PWN": open(message_filename, "rb")
        }

        try:
            req = requests.post(self.discord_webhook_url, files=image_file)
        except Exception as err:
            self.log.error("Failed to send Discord message")
            self.log.error(traceback.print_exc())

    def create_image(self, htb_name, htb_user_avatar_url, htb_flag_type, message):
        """
        Create notification image. The image will consist of HTB user avatar, frame layers over the avatar,
        message describing flag obtained and image of the Flag.
        htb_flag_type - parameters is URL of the machine or type of the challenge.
        """

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
        green_color = (134, 190, 60)
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
            font_htb_name = ImageFont.truetype(
                "../images/" + self.font_htb_name,
                size=font_htb_name_size,
                layout_engine=0
            )
            if font_htb_name.getlength(htb_name) < 300:
                x_pos = width // 2 - font_htb_name.getlength(htb_name) // 2 + 5
                image_editable.text((x_pos, margin_size), htb_name, fill=white_color, font=font_htb_name)
                break
            else:
                font_htb_name_size -= 1

        font_message = ImageFont.truetype("../images/" + self.font_message, size=18, layout_engine=0)
        if message[1] == "ROOT " or message[1] == "USER ":
            # Machine message
            x_pos_1 = width // 2 - font_message.getlength("".join(message)) // 2 + 5
            x_pos_2 = x_pos_1 + font_message.getlength(message[0])
            x_pos_3 = x_pos_2 + font_message.getlength(message[1])

            image_editable.text((x_pos_1, 70), message[0], fill=white_color, font=font_message)
            if message[1] == "ROOT ":
                image_editable.text((x_pos_2, 70), message[1], fill=red_color, font=font_message)
            else:
                image_editable.text((x_pos_2, 70), message[1], fill=green_color, font=font_message)
            image_editable.text((x_pos_3, 70), message[2], fill=white_color, font=font_message)
        else:
            # Challenge, endgame or fortress message
            x_pos_1 = width // 2 - font_message.getlength("".join([message[0], message[1]])) // 2 + 5
            x_pos_2 = x_pos_1 + font_message.getlength("".join(message[0]))
            x_pos_3 = width // 2 - font_message.getlength(message[2]) // 2 + 5

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

    def send_member_solves_messages(self):
        """
        Sort saved messages and send them.
        """

        self.log.info("Message queue - " + str(len(self.message_queue)))

        if self.message_queue:
            sorted_message_queue = OrderedDict(sorted(self.message_queue.items()))
            for _, message_data in sorted_message_queue.items():
                self.send_message(
                    message_data["member_id"],
                    message_data["member_name"],
                    message_data["activity_data"]
                )

        # Always empty message queue
        self.message_queue = {}


    def send_message(self, member_id, htb_name, activity_data):
        """
        Send message in Discord using Webhook.
        """

        self.log.info("        Sending message for user {} ({})".format(htb_name, member_id))

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
                req = requests.post(self.discord_webhook_url, files=image_file)
            except Exception as err:
                self.log.error("Failed to send Discord message")
                self.log.error(traceback.print_exc())


def main():
    settings = read_settings_file("settings/PWNgress_settings.cfg")
    PWNgress(settings["HTB_APP_TOKEN"], settings["HTB_TEAM_ID"], settings["DISCORD_WEBHOOK_URL"],
             settings["FONT_HTB_NAME"], settings["FONT_MESSAGE"], settings["HTB_USERS_TO_IGNORE"])


if __name__ == "__main__":
    main()
