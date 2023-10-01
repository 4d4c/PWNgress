from collections import OrderedDict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import json
import os
import re
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

    def __init__(self, htb_app_token, htb_team_id, discord_webhook_url_team, discord_webhook_url_alerts,
                 font_htb_name, font_message, htb_users_to_ignore, font_table_header, font_table_names,
                 font_table_data):
        self.log = Lumberjack("../logs/PWNgress_events.log", False)

        self.db = SQLWizard("../database/PWNgress.sqlite")

        self.log.info("PWNgress started")

        self.htb_app_token = htb_app_token
        self.htb_team_id = htb_team_id
        self.discord_webhook_url_team = discord_webhook_url_team
        self.discord_webhook_url_alerts = discord_webhook_url_alerts
        self.font_htb_name = font_htb_name
        self.font_message = font_message
        self.htb_users_to_ignore = htb_users_to_ignore.split(",")
        self.font_table_header = font_table_header
        self.font_table_names = font_table_names
        self.font_table_data = font_table_data

        self.message_queue = {}

        self.loop()

    def loop(self):
        """
        Core part of the script. Currently, only tracking team activities is implemented.
        """

        last_rank_check_date = ""
        while True:
            self.get_and_save_team_members()
            self.check_each_team_member_solves()
            self.send_member_solves_messages()

            # Only run once a week at 01:00 UTC
            if datetime.today().weekday() == 5:
                if datetime.now().time().strftime("%H") == "01":
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    self.log.debug("Starting ranking check")
                    self.log.debug("    Current date   : {}".format(current_date))
                    self.log.debug("    Last check date: {}".format(last_rank_check_date))
                    if current_date != last_rank_check_date:
                        self.get_team_ranking()
                        self.get_members_ranking()
                        self.send_ranking_message()
                        last_rank_check_date = current_date

            # We don't want to check pwns every minute through the week. Check pwns every minute from
            # Sat 19:00 UTC to Sun 07:00. On all other days check every 30 minutes
            self.log.debug("Day - {}".format(datetime.today().weekday()))
            self.log.debug("Hour - {}".format(int(datetime.now().time().strftime("%H"))))
            if datetime.today().weekday() == 5 and int(datetime.now().time().strftime("%H")) >= 19 or\
               datetime.today().weekday() == 6 and int(datetime.now().time().strftime("%H")) <= 7:
                self.log.info("Sleeping for {} sec".format(60))
                time.sleep(60)
            else:
                self.log.info("Sleeping for {} sec".format(60 * 30))
                time.sleep(60 * 30)

    def error_handler(self, error_message, traceback_message):
        """
        Send error message to Discord server using webhook (DISCORD_WEBHOOK_URL_ALERTS).
        """

        self.log.error(error_message)
        self.log.error(traceback_message)

        try:
            headers = {
                "Content-Type": "application/json"
            }

            message_data = {
                "content": "```" + "[-] ERROR: " + error_message + "\n\n" + traceback_message + "```"
            }

            req = requests.post(self.discord_webhook_url_alerts, headers=headers, json=message_data)
        except Exception as err:
            self.log.error("Failed to send an alert message " + str(err))
            self.log.error(traceback.format_exc())

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
            self.error_handler("Failed to get team members " + str(err), traceback.format_exc())
            return

        # with open("test/test_team_members.json", "w") as f:
        #     json.dump(team_members_json_data, f)
        # with open("test/test_team_members.json", "r") as f:
        #     team_members_json_data = json.load(f)

        all_member_ids = [x[0] for x in self.db.select("id", "htb_team_members")]

        for member_data in team_members_json_data:
            # Ignore inactive users
            if str(member_data["id"]) in self.htb_users_to_ignore:
                self.log.warning("Ignoring user {} ({})".format(
                    member_data["name"],
                    member_data["id"]
                ))
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

        # Check if we need to delete any users (user left the team)
        all_members_in_htb = [member_data["id"] for member_data in team_members_json_data]
        users_to_remove = list(set(all_member_ids) - set(all_members_in_htb))
        for user_to_remove in users_to_remove:
            self.log.warning("Deleting user {}".format(user_to_remove))
            self.db.delete(
                "htb_team_members",
                "id = '{}'".format(user_to_remove)
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

        self.log.debug("Checking user activities {} ({})".format(member_name, user_id))

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
            self.error_handler("Failed to get member activities " + str(err), traceback.format_exc())
            return ""

    def get_team_ranking(self):
        """
        """

        self.log.info("Getting team ranking")

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
            self.error_handler("Failed to get team ranking data " + str(err), traceback.format_exc())
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

        self.log.info("Getting members ranking")

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
                self.error_handler("Failed to get member ranking data " + str(err), traceback.format_exc())
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

        # last_two_ranking_data = self.db.select(
        #     "*",
        #     "team_ranking",
        #     "rank > 0 ORDER BY rank_date DESC LIMIT 2"
        # )

        # diff_rank = last_two_ranking_data[0][1] - last_two_ranking_data[1][1]
        # diff_points = last_two_ranking_data[0][2] - last_two_ranking_data[1][2]
        # diff_user_owns = last_two_ranking_data[0][3] - last_two_ranking_data[1][3]
        # diff_system_owns = last_two_ranking_data[0][4] - last_two_ranking_data[1][4]
        # diff_challenge_owns = last_two_ranking_data[0][5] - last_two_ranking_data[1][5]
        # diff_respects = last_two_ranking_data[0][6] - last_two_ranking_data[1][6]
        # team_message = "```plaintext\n"
        # team_message += "+-----------------------------------------------------------------------------------------------------+\n"
        # team_message += "|                                            TEAM RANKING                                             |\n"
        # team_message += "+----------------+----------------+----------------+----------------+----------------+----------------+\n"
        # team_message += "|      RANK      |     POINTS     |   USERS OWNS   |   SYSTEM OWNS  | CHALLENGE OWNS |    RESPECTS    |\n"
        # team_message += "+----------------+----------------+----------------+----------------+----------------+----------------+\n"

        # team_message += "|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|{:>16s}|\n".format(
        #     "{} ({})".format(last_two_ranking_data[0][1], diff_rank),
        #     "{} ({})".format(last_two_ranking_data[0][2], diff_points),
        #     "{} ({})".format(last_two_ranking_data[0][3], diff_user_owns),
        #     "{} ({})".format(last_two_ranking_data[0][4], diff_system_owns),
        #     "{} ({})".format(last_two_ranking_data[0][5], diff_challenge_owns),
        #     "{} ({})".format(last_two_ranking_data[0][6], diff_respects)
        # )
        # team_message += "+-----------------------------------------------------------------------------------------------------+\n"
        # team_message += "```\n"

        # headers = {
        #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
        #                   "Gecko/20100101 Firefox/111.0",
        #     "Content-Type": "application/json"
        # }

        # message_data = {
        #     "content": team_message
        # }
        # try:
        #     req = requests.post(self.discord_webhook_url, headers=headers, json=message_data)
        # except Exception as err:
        #     self.log.error("Failed to send Discord message")
        #     self.log.error(traceback.format_exc())

        # Get 25 team members from the database. We limit it to 25 so ranking image doesn't get too big
        found_member_rows = self.db.select(
            "id",
            "htb_team_members",
            "id > 0 ORDER by rank ASC LIMIT 25"
        )
        # Get list of avatar links of the team members
        avatar_links = [x[0] for x in self.db.select(
            "htb_avatar",
            "htb_team_members",
            "id > 0 ORDER by rank ASC LIMIT 25"
        )]
        # Ranking table data. Start with headers
        table_data = [["NAME", "RNK", "PNT", "USR", "SYS", "CHL", "FRT", "END", "PRO"]]
        for found_member_row in found_member_rows:
            member_id = found_member_row[0]
            # Get two most recent rank rows for each member
            last_two_ranking_data = self.db.select(
                "*",
                "member_ranking",
                "id = {} ORDER BY rank_date DESC LIMIT 2".format(member_id)
            )

            last_two_ranking_data_first = last_two_ranking_data[0]
            # If it's a new member we don't have previous weeks data. Add all user ranking as 0 (no changes)
            if len(last_two_ranking_data) == 1:
                last_two_ranking_data_second = last_two_ranking_data[0]
            else:
                last_two_ranking_data_second = last_two_ranking_data[1]
            diff_rank = last_two_ranking_data_first[3] - last_two_ranking_data_second[3]
            diff_points = last_two_ranking_data_first[4] - last_two_ranking_data_second[4]
            diff_user_owns = last_two_ranking_data_first[5] - last_two_ranking_data_second[5]
            diff_system_owns = last_two_ranking_data_first[6] - last_two_ranking_data_second[6]
            diff_challenge_owns = last_two_ranking_data_first[7] - last_two_ranking_data_second[7]
            diff_fortress_owns = last_two_ranking_data_first[8] - last_two_ranking_data_second[8]
            diff_endgame_owns = last_two_ranking_data_first[9] - last_two_ranking_data_second[9]
            diff_prolab_owns = last_two_ranking_data_first[10] - last_two_ranking_data_second[10]
            # diff_user_bloods = last_two_ranking_data_first[11] - last_two_ranking_data_second[11]
            # diff_system_bloods = last_two_ranking_data_first[12] - last_two_ranking_data_second[12]
            # diff_respects = last_two_ranking_data_first[14] - last_two_ranking_data_second[14]

            table_data.append([
                last_two_ranking_data[0][2],
                "{} ({:+d})".format(last_two_ranking_data_first[3], diff_rank).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[4], diff_points).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[5], diff_user_owns).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[6], diff_system_owns).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[7], diff_challenge_owns).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[8], diff_fortress_owns).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[9], diff_endgame_owns).replace("(+0)", "(0)"),
                "{} ({:+d})".format(last_two_ranking_data_first[10], diff_prolab_owns).replace("(+0)", "(0)"),
                # "{} ({:+d})".format(last_two_ranking_data_first[12], diff_user_bloods),
                # "{} ({:+d})".format(last_two_ranking_data_first[12], diff_system_bloods),
                # "{} ({:+d})".format(last_two_ranking_data_first[14], diff_respects),
                # datetime.strftime(datetime.strptime(last_two_ranking_data_first[13], "%Y-%m-%dT%H:%M:%S.%fZ"), "%Y-%m-%d")
            ])

        table_filename = self.create_table_image(table_data, avatar_links)

        image_file = {
            "PWN": open(table_filename, "rb")
        }

        try:
            req = requests.post(self.discord_webhook_url_team, files=image_file)
        except Exception as err:
            self.error_handler("Failed to send Discord message " + str(err), traceback.format_exc())

    def create_table_image(self, table_data, avatar_links):
        """
        Create ranking table image. Based on https://gist.github.com/xiaopc/324acb627e6f1f019ab60b0ec0e355aa
        """

        table_filename = "/tmp/PWNrank.png"
        colors = {
            "background": (43, 45, 49),
            "header_background": (38, 38, 38),
            "font": (159, 239, 0),
            "line": (0, 0, 0),
            "red": (245, 59, 60),
            "green": (167, 253, 48),
            "data": (240, 240, 240),
            "names": (255, 255, 255),
            "header_colors": [
                (255, 255, 255),
                (191, 147, 23),
                (0, 176, 240),
                (146, 208, 80),
                (255, 0, 0),
                (159, 239, 0),
                (148, 0, 255),
                (0, 134, 255),
                (255, 192, 0)
            ]
        }
        margin = 5

        row_max_hei = [0] * len(table_data)
        col_max_wid = [0] * len(max(table_data, key=len))

        for i in range(len(table_data)):
            for j in range(len(table_data[i])):
                # Header font
                if i == 0:
                    font = ImageFont.truetype(self.font_table_header, size=26, layout_engine=0)
                    row_max_hei[i] = max(round(font.getbbox(table_data[i][j])[3]) + 5, row_max_hei[i])
                else:
                    if j == 0:
                        # Names font
                        font = ImageFont.truetype(self.font_table_names, size=28, layout_engine=0)
                        # Add spacing to data cell to add up/down arrows if needed
                        col_max_wid[j] = max(round(font.getlength(table_data[i][j])) + 33, col_max_wid[j])
                    else:
                        # Data font
                        font = ImageFont.truetype(self.font_table_data, size=22, layout_engine=0)
                        col_max_wid[j] = max(round(font.getlength(table_data[i][j])) + 30, col_max_wid[j])
                    row_max_hei[i] = max(round(font.getbbox(table_data[i][j])[3]), row_max_hei[i])

        tab_width = sum(col_max_wid) + len(col_max_wid) * 2 * margin
        tab_heigh = sum(row_max_hei) + len(row_max_hei) * 2 * margin

        tab = Image.new(
            "RGBA",
            (tab_width + margin + margin, tab_heigh + margin + margin),
            colors["background"]
        )
        draw = ImageDraw.Draw(tab)

        draw.rectangle(
            [(margin, margin), (margin + tab_width, margin + tab_heigh)],
            fill=colors["background"],
            width=0
        )
        draw.rectangle(
            [
                (margin, margin),
                (margin + tab_width, margin + row_max_hei[0] + margin * 2)
            ],
            fill=colors["header_background"],
            width=0
        )

        top = margin
        for row_h in row_max_hei:
            draw.line([(margin, top), (tab_width + margin, top)], fill=colors["line"])
            top += row_h + margin * 2
        draw.line([(margin, top), (tab_width + margin, top)], fill=colors["line"])

        left = margin
        for col_w in col_max_wid:
            draw.line([(left, margin), (left, tab_heigh + margin)], fill=colors["line"])
            left += col_w + margin * 2
        draw.line([(left, margin), (left, tab_heigh + margin)], fill=colors["line"])

        top, left = margin + margin, 0
        for i in range(len(table_data)):
            left = margin + margin
            for j in range(len(table_data[i])):
                if i == 0:
                    color = colors["header_colors"][j]
                    font = ImageFont.truetype(self.font_table_header, size=26, layout_engine=0)
                else:
                    if j == 0:
                        font = ImageFont.truetype(self.font_table_names, size=28, layout_engine=0)
                        color = colors["names"]
                    else:
                        font = ImageFont.truetype(self.font_table_data, size=22, layout_engine=0)
                        color = colors["data"]
                if "-" in table_data[i][j]:
                    if j == 1:
                        color = colors["green"]
                    else:
                        color = colors["red"]
                elif "+" in table_data[i][j]:
                    if j == 1:
                        color = colors["red"]
                    else:
                        color = colors["green"]
                _left = left
                if i == 0:
                    _left += (col_max_wid[j] - round(font.getlength(table_data[i][j]))) // 2
                elif i != 0 and j != 0:
                    _left += col_max_wid[j] - round(font.getlength(table_data[i][j]))
                if j == 0:
                    if i == 0:
                        draw.text((_left, top), table_data[i][j], font=font, fill=color)
                    else:
                        draw.text((_left + 33, top-3), table_data[i][j], font=font, fill=color)
                else:
                    if i == 0:
                        draw.text((_left, top), table_data[i][j], font=font, fill=color)
                    else:
                        if "-" in table_data[i][j]:
                            if j == 1:
                                with open("../images/arrow_up.png", "rb") as f:
                                    arrow_image = Image.open(io.BytesIO(f.read()))
                            else:
                                with open("../images/arrow_down.png", "rb") as f:
                                    arrow_image = Image.open(io.BytesIO(f.read()))
                            new_arrow_image = Image.new("RGBA", arrow_image.size, colors["background"])
                            new_arrow_image.paste(arrow_image, (0, 0), arrow_image)
                            new_arrow_image.thumbnail((25, 25))
                            tab.paste(new_arrow_image, (_left - 28, top - 1))
                        elif "+" in table_data[i][j]:
                            if j == 1:
                                with open("../images/arrow_down.png", "rb") as f:
                                    arrow_image = Image.open(io.BytesIO(f.read()))
                            else:
                                with open("../images/arrow_up.png", "rb") as f:
                                    arrow_image = Image.open(io.BytesIO(f.read()))
                            new_arrow_image = Image.new("RGBA", arrow_image.size, colors["background"])
                            new_arrow_image.paste(arrow_image, (0, 0), arrow_image)
                            new_arrow_image.thumbnail((25, 25))
                            tab.paste(new_arrow_image, (_left - 28, top - 1))
                        draw.text((_left, top), table_data[i][j], font=font, fill=color)
                left += col_max_wid[j] + margin * 2
            top += row_max_hei[i] + margin * 2

        # HTTP headers for image downloading
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
                          "Gecko/20100101 Firefox/111.0"
        }
        indent = 0

        for avatar_link in avatar_links:
            # Download HTB user image
            try:
                req = requests.get(avatar_link, headers=headers)
            except Exception as err:
                self.error_handler("Failed to get member image " + str(err), traceback.format_exc())

            htb_avatar_image = Image.open(io.BytesIO(req.content))

            # filename = avatar_link.split("/")[-1:][0]
            # with open("/tmp/" + filename, "rb") as f:
            #     htb_avatar_image = Image.open(io.BytesIO(f.read()))
            #     f.write(req.content)

            htb_avatar_image.thumbnail((25, 25))
            tab.paste(htb_avatar_image, (10, 49 + indent))
            indent += 31

        # tab.show()
        tab.save(table_filename)

        return table_filename

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
        tmp_htb_name = re.sub('[^a-zA-Z0-9]+', '', htb_name).upper()
        tmp_message_1 = re.sub('[^a-zA-Z0-9]+', '', message[1]).upper()
        tmp_message_2 = re.sub('[^a-zA-Z0-9]+', '', message[2]).replace("machine", "").replace("challenge", "").upper()
        notification_filename = "/tmp/{}-{}-{}.png".format(tmp_htb_name, tmp_message_1, tmp_message_2)

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
            self.error_handler("Failed to get member image " + str(err), traceback.format_exc())
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
                self.error_handler("Failed to get machine image " + str(err), traceback.format_exc())
                return False
        else:
            # If it's challenge, endgame or fortress flag we use local image
            machine_img = Image.open("../images/{}.png".format(htb_flag_type.lower()))

        new_machine_img = Image.new("RGBA", machine_img.size, background_color)
        new_machine_img.paste(machine_img, (0, 0), machine_img)
        new_machine_img.thumbnail((flag_size, flag_size))
        background_layer.paste(new_machine_img, (width - flag_size - margin_size, margin_size), new_machine_img)

        # Frame image
        frame_img = Image.open("../images/avatar_frame.png").convert("RGBA")
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
                self.font_htb_name,
                size=font_htb_name_size,
                layout_engine=0
            )
            if font_htb_name.getlength(htb_name) < 300:
                x_pos = width // 2 - font_htb_name.getlength(htb_name) // 2 + 5
                image_editable.text((x_pos, margin_size), htb_name, fill=white_color, font=font_htb_name)
                break
            else:
                font_htb_name_size -= 1

        font_message = ImageFont.truetype(self.font_message, size=18, layout_engine=0)
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
        try:
            notification_filename = self.create_image(htb_name, htb_user_avatar_url, htb_flag_type, message)
        except Exception as err:
            notification_filename = False
            self.error_handler("Failed to create notification image " + str(err), traceback.format_exc())
            return False

        # Send image to Discord
        if notification_filename:
            image_file = {
                "PWN": open(notification_filename, "rb")
            }

            try:
                req = requests.post(self.discord_webhook_url_team, files=image_file)
            except Exception as err:
                self.error_handler("Failed to send Discord message " + str(err), traceback.format_exc())

            os.remove(notification_filename)

def main():
    settings = read_settings_file("settings/PWNgress_settings.cfg")
    PWNgress(settings["HTB_APP_TOKEN"], settings["HTB_TEAM_ID"], settings["DISCORD_WEBHOOK_URL_TEAM"],
             settings["DISCORD_WEBHOOK_URL_ALERTS"], settings["FONT_HTB_NAME"], settings["FONT_MESSAGE"],
             settings["HTB_USERS_TO_IGNORE"], settings["FONT_TABLE_HEADER"], settings["FONT_TABLE_NAMES"],
             settings["FONT_TABLE_DATA"])


if __name__ == "__main__":
    main()
