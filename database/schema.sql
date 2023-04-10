CREATE TABLE IF NOT EXISTS htb_team_members (
    id INT,
    htb_name TEXT,
    discord_name TEXT,
    htb_avatar TEXT,
    last_flag_date TEXT,
    points INT,
    rank INT,
    json_data TEXT
);

CREATE TABLE IF NOT EXISTS team_ranking (
    rank_date TEXT,
    rank INT,
    points INT,
    user_count INT,
    root_count INT,
    challenge_count INT,
    respect_count INT
);

CREATE TABLE IF NOT EXISTS member_ranking (
    rank_date TEXT,
    id INT,
    user_count INT,
    root_count INT,
    machine_count INT,
    challenge_count INT,
    fortress_count INT,
    endgame_count INT,
    prolabs_count INT,
    respect_count INT
);
