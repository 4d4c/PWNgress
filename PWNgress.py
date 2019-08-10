import sys
from collections import OrderedDict

import discord
from lumberjack.lumberjack import Lumberjack
from utils.utils import read_settings_file
from SQLWizard.sqlwizard import SQLWizard


class PWNgress(discord.Client):
    """
    PWNgress.
    """

    def __init__(self, discord_token, db_filename, notifications=False):
        self.log = Lumberjack("log/events.log", True)

        self.db = SQLWizard(db_filename)

        self.notifications = notifications

        super().__init__()
        self.run(discord_token)


    async def on_ready(self):
        """
        Print state when PWNgress is ready. If class started with notification parameter,
        send the messages and kill the process.
        """

        self.log.info("PWNgress started")

        if self.notifications:
            for notification in self.notifications:
                await self.send_pwn_notification(*notification)

            sys.exit(1)


    async def on_message(self, message):
        """
        Parse any message except own. If message starts with .status - delete it and return
        information about the box.
        """

        if self.notifications:
            return False

        if message.author == self.user:
            return False

        channel_name = message.channel.name.lower()

        self.log.info("Processing message from {} on {} channel".format(str(message.author), channel_name))

        if channel_name != "pwngress":
            return False

        self.log.debug("Message content: " + message.content)

        if not message.content.startswith(".status"):
            return False

        htb_name = self.get_htb_name(str(message.author))
        if not htb_name:
            return False

        await message.channel.delete_messages([message])

        if len(message.content.split(" ")) == 2:
            box_name = message.content.split(" ")[1]

            box_embed_info = self.get_box_embed_info(box_name)

            if not box_embed_info:
                self.log.error("Creating box embed information failed for " + box_name)
                return False

            self.log.info("Sent embed message for " + box_name)
            await message.channel.send("", embed=box_embed_info)

            return True

        if len(message.content.split(" ")) == 3:
            box_name = message.content.split(" ")[1]
            box_status = self.get_box_status_from_user_input(message.content.split(" ")[2])

            box_data = self.db.select("*", "boxes", "name = '{}".format(box_name))
            if not box_data:
                self.log.error("Box was not found - " + box_name)
                return False

            # TODO: Change this
            new_data = {}

            if box_data[0][3]:
                wts = box_data[0][3].replace(htb_name + ",", "").replace(htb_name, "")
            else:
                wts = "-"
            if box_data[0][4]:
                working = box_data[0][4].replace(htb_name + ",", "").replace(htb_name, "")
            else:
                working = "-"
            if box_data[0][5]:
                user = box_data[0][5].replace(htb_name + ",", "").replace(htb_name, "")
            else:
                user = "-"
            if box_data[0][6]:
                root = box_data[0][6].replace(htb_name + ",", "").replace(htb_name, "")
            else:
                root = "-"

            new_data["wts"] = wts if wts else "-"
            new_data["working"] = working if working else "-"
            new_data["user"] = user if user else "-"
            new_data["root"] = root if root else "-"

            if new_data[box_status] and new_data[box_status] != "-":
                new_data[box_status] += "," + htb_name
            else:
                new_data[box_status] = htb_name

            self.db.update(
                "boxes",
                OrderedDict([
                    ("wts", new_data["wts"]),
                    ("working", new_data["working"]),
                    ("user", new_data["user"]),
                    ("root", new_data["root"])
                ]),
                "name = '{}'".format(box_name)
            )
            self.log.info("Box status updated - " + box_name)

            # Send messages to WTS group
            if box_status == "wts":
                wts_users = new_data["wts"].replace(htb_name + ",", "").replace(htb_name, "")

                if wts_users:
                    for wts_user in wts_users.split(","):
                        if not wts_user.strip() or wts_user == str(message.author) or wts_user.strip() == "-":
                            continue

                        discord_id = self.get_discord_id(wts_user)
                        user_obj = self.get_user(int(discord_id))
                        message_data = "Hi {}. {} wants to start pwning {} box :)".format(wts_user, message.author, box_name)
                        await user_obj.send(message_data)

                        self.log.info("Sent message to {} ({})".format(wts_user, discord_id))

            return True

        return False


    @staticmethod
    def get_box_status_from_user_input(box_status):
        """
        Get correct status of the box.
        """

        if box_status.lower() in ["wts", "s"]:
            return "wts"

        if box_status.lower() in ["working", "w"]:
            return "working"

        if box_status.lower() in ["user", "u"]:
            return "user"

        if box_status.lower() in ["root", "r"]:
            return "root"

        return False


    def create_new_box(self, box_name, box_score="?/10",
                       box_image="https://www.hackthebox.eu/images/favicon.png",
                       wts="", working="", user="", root=""):
        """
        Create new box in the database.
        """

        self.db.insert(
            "boxes",
            OrderedDict([
                ("name", box_name),
                ("score", box_score),
                ("image", box_image),
                ("wts", wts),
                ("working", working),
                ("user", user),
                ("root", root)
            ])
        )


    def get_htb_name(self, discord_name):
        """
        Get HTB name of the user.
        """

        htb_name = self.db.select("*", "names", "discord_name = '{}'".format(str(discord_name).lower()))

        if htb_name:
            self.log.debug("HTB name: " + htb_name[0][1])
            return htb_name[0][1]

        self.log.error("HTB name was not found - " + discord_name)
        return False


    def get_discord_name(self, htb_name):
        """
        Get Discord name of the user.
        """

        discord_name = self.db.select("*", "names", "htb_name = '{}'".format(htb_name))

        if discord_name:
            self.log.debug("Discord name: " + discord_name[0][2])
            return discord_name[0][2]

        self.log.error("Discord name was not found - " + htb_name)
        return False


    def get_discord_id(self, name):
        """
        Get Discord ID of the user.
        """

        discord_id = self.db.select("*", "names", "discord_name = '{name}' or htb_name = '{name}'".format(name=name))

        if discord_id:
            self.log.debug("Discord ID: " + discord_id[0][0])
            return discord_id[0][0]

        self.log.error("Discord ID was not found - " + name)
        return False


    @staticmethod
    def split_usernames(username_list):
        """
        Add new lines after each two usernames. Return "-" if empty
        """

        if not username_list:
            return "-"

        if "," in username_list:
            output = ""
            for index, usernames in enumerate(username_list.split(",")):
                output += usernames

                if (index - 1) % 2 == 0:
                    output += "\n"
                else:
                    output += " "

            return output

        return username_list


    def get_box_embed_info(self, box_name):
        """
        Get status information for the box by box name.
        """

        box_data = self.db.select("*", "boxes", "name = '{}'".format(box_name))

        if box_data:
            embed = discord.Embed(title=box_data[0][0].upper(), description=box_data[0][1], color=0x2B78E3)
            embed.set_thumbnail(url=box_data[0][2])
            embed.add_field(name="W.T.S.", value=self.split_usernames(box_data[0][3]), inline=True)
            embed.add_field(name="WORKING", value=self.split_usernames(box_data[0][4]), inline=True)
            embed.add_field(name="USER", value=self.split_usernames(box_data[0][5]), inline=True)
            embed.add_field(name="ROOT", value=self.split_usernames(box_data[0][6]), inline=True)

            return embed

        return False


    async def send_pwn_notification(self, channel, username, action, box_name):
        channel = self.get_channel(int(channel))
        self.log.info("Sending notification for {} on {} ({})".format(action, box_name, username))
        await channel.send("User {} owned {} on {}!".format(username, action, box_name))


def main():
    settings = read_settings_file("settings.cfg")
    PWNgress(settings["TOKEN"], settings["DB_FILENAME"])


if __name__ == '__main__':
    main()
