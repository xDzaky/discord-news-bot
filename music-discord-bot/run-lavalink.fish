#!/usr/bin/env fish

set project_root /home/dzaky/Desktop/coding-project/music-discord-bot
set lavalink_dir $project_root/Vocard/lavalink
set lavalink_jar $project_root/Lavalink.jar

if not test -f "$lavalink_jar"
    echo "Lavalink.jar not found at $lavalink_jar"
    echo "Download it with:"
    echo "curl -L -o $lavalink_jar https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar"
    exit 1
end

cd $lavalink_dir
java -jar $lavalink_jar
