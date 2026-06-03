CREATE DATABASE CricketAnalytics;
GO
use CricketAnalytics
GO 
drop table if exists deliveries
drop table if exists matches
go 
create table matches(
    match_id int PRIMARY key,
    season nvarchar(20) not null,
    start_data date not null,
    event nvarchar(100) not null,
    venue nvarchar(100),
    city nvarchar(100),
    toss_winner nvarchar(100) not NULL,
    player_of_match nvarchar(100),
    winner nvarchar(100),
    winner_runs int,
    winner_wickets int 
);
go 

CREATE TABLE deliveries(
    delivery_id bigint identity(1,1) primary key,
    match_id int not null 
    season nvarchar(20) not null,
    start_date date not null,
    venue nvarchar(200) not null,
    innings int not null 
    ball decimal(4,1) not null,
    batting_team nvarchar(100) not null,
    bowling_team nvarchar(100) not null,
    striker nvarchar(100) not null,
    non_striker nvarchar(100) not null,
    bowler nvarchar(100) not null,
    runs_off_bat int not null,
    extras int not null,
    wides int,
    noballs int,
    byes int,
    legbyes int,
    penalty int,
    wicket_type nvarchar(50)
    player_dismissed nvarchar(100),
    other_wicket_type nvarchar(50)
    other_player_dismissed nvarchar(100)
    constraint FK_deliveries_matches
    foreign key(match_id)
    REFERENCES matches(match_id)
)
go   
