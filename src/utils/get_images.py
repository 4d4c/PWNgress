import requests
from cairosvg import svg2png


def download_challenge_images():
    challenge_url = "https://app.hackthebox.com/images/icons/ic-challenge-categ/ic-{}.svg"

    challenge_types = [
        "crypto",
        "forensics",
        "gamepwn",
        "hardware",
        "misc",
        "mobile",
        "osint",
        "pwn",
        "reversing",
        "web",

        "fortress",

        "endgame"
    ]

    for challenge_type in challenge_types:
        svg_url = challenge_url.format(challenge_type)

        # Save SVG image
        # req = requests.get(svg_url)
        # with open("../../images/" + challenge_type + ".svg", "wb") as svg_file:
        #     svg_file.write(req.content)

        # Read the local image. Used for testing
        with open("../../images/" + challenge_type + ".svg", "r") as svg_file:
            svg_data = svg_file.read()

        # Change color
        if challenge_type == "fortress":
            svg_data = svg_data.replace("#A4B1CD", "#9400ff")
        elif challenge_type == "endgame":
            svg_data = svg_data.replace("#A4B1CD", "#0086ff")
        else:
            svg_data = svg_data.replace("#A4B1CD", "#9FEF00")
        # 2e86ab

        # Save image to png
        svg2png(bytestring=svg_data, write_to="../../images/" + challenge_type + ".png", output_height=75, output_width=75)


download_challenge_images()
