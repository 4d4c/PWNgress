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
    user_owns INT,
    system_owns INT,
    challenge_owns INT,
    respects INT
);

CREATE TABLE IF NOT EXISTS member_ranking (
    id INT,
    rank_date TEXT,
    htb_name TEXT,
    rank INT,
    points INT,
    user_owns INT,
    system_owns INT,
    challenge_owns INT,
    fortress_owns INT,
    endgame_owns INT,
    prolabs_owns INT,
    user_bloods INT,
    system_bloods INT,
    last_flag_date INT,
    respects INT
);
