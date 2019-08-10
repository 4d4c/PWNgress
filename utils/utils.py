import os
import sys
import requests
import re


def read_settings_file(settings_filepath):
    """
    Read settings file and return Discord token.
    """

    if not os.path.exists(settings_filepath):
        print("[-] ERROR: Settings file is missing")
        sys.exit(1)

    with open(settings_filepath, "r") as settings_file:
        settings = settings_file.read().splitlines()

    return dict(setting.split('=') for setting in settings)


class HTBhelper():
    """
    HTB helper.
    """

    def __init__(self, username, password, api_token=""):
        self.username = username
        self.password = password
        self.api_token = api_token

        self.session = requests.session()
        self.session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.85 Safari/537.36"
        }


    def login(self):
        req = self.session.get("https://www.hackthebox.eu/login")

        html = req.text
        csrf_token = re.findall(r'type="hidden" name="_token" value="(.+?)"', html)

        if not csrf_token:
            return False

        data = {
            "_token": csrf_token[0],
            "email": self.username,
            "password": self.password
        }
        req = self.session.post("https://www.hackthebox.eu/login", data=data)

        if req.status_code == 200:
            return True

        return False


    def get_user_info(self, url):
        req = self.session.get(url)
        html = req.text

        username = re.findall(r'Hack The Box :: (.+?)<', html)
        users = re.findall(r'owned user.+?machines/profile/\d+">(.+?)</a>', html)
        roots = re.findall(r'owned root.+?machines/profile/\d+">(.+?)</a>', html)

        return username[0].strip(), users, roots


    def get_all_machines(self):
        url = "https://www.hackthebox.eu/api/machines/get/all/?api_token=" + self.api_token

        req = self.session.get(url)

        if req.status_code == 200:
            return req.text

        return False


    def get_machine_score(self, machine_id):
        url = "https://www.hackthebox.eu/home/machines/profile/" + str(machine_id)

        req = self.session.get(url)

        if req.status_code == 200:
            score = re.findall(r'Difficulty: (.+?/10)', req.text)
            if score:
                return score[0]

        return "?/10"


    def get_pwns(self):
        url = "https://www.hackthebox.eu/api/shouts/get/initial/html/50?api_token=" + self.api_token

        req = self.session.post(url)

        if req.status_code == 200:
            html = req.text

            users = re.findall(r'\d+\\">(?P<name>.{1,20}?)<\\\/a>\sowned\suser\son\s<.+?">(?P<asd>.+?)<\\\/', html)
            roots = re.findall(r'\d+\\">(?P<name>.{1,20}?)<\\\/a>\sowned\sroot\son\s<.+?">(?P<asd>.+?)<\\\/', html)

            return users, roots

        return [], []
