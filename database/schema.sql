CREATE DATABASE CricketAnalytics;
GO

USE CricketAnalytics;
GO

DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS matches;
GO

CREATE TABLE matches (
    match_id INT PRIMARY KEY,
    season NVARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    event NVARCHAR(100) NOT NULL,
    venue NVARCHAR(200) NOT NULL,
    city NVARCHAR(100),
    toss_winner NVARCHAR(100) NOT NULL,
    toss_decision NVARCHAR(20) NOT NULL,
    player_of_match NVARCHAR(100),
    winner NVARCHAR(100),
    winner_runs INT,
    winner_wickets INT
);
GO

CREATE TABLE deliveries (
    delivery_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    match_id INT NOT NULL,
    season NVARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    venue NVARCHAR(200) NOT NULL,
    innings INT NOT NULL,
    ball DECIMAL(4,1) NOT NULL,
    batting_team NVARCHAR(100) NOT NULL,
    bowling_team NVARCHAR(100) NOT NULL,
    striker NVARCHAR(100) NOT NULL,
    non_striker NVARCHAR(100) NOT NULL,
    bowler NVARCHAR(100) NOT NULL,
    runs_off_bat INT NOT NULL,
    extras INT NOT NULL,
    wides INT,
    noballs INT,
    byes INT,
    legbyes INT,
    penalty INT,
    wicket_type NVARCHAR(50),
    player_dismissed NVARCHAR(100),
    other_wicket_type NVARCHAR(50),
    other_player_dismissed NVARCHAR(100),

    CONSTRAINT FK_deliveries_matches
        FOREIGN KEY (match_id)
        REFERENCES matches(match_id)
);
GO