"""Static content for the games cog: trivia, hangman words, 8-ball and more."""

# category -> list of (question, options, correct index)
TRIVIA: dict[str, list[tuple[str, list[str], int]]] = {
    "general": [
        ("How many continents are there on Earth?", ["5", "6", "7", "8"], 2),
        (
            "Which planet is known as the Red Planet?",
            ["Venus", "Mars", "Jupiter", "Mercury"],
            1),
        (
            "What is the largest ocean on Earth?",
            ["Atlantic", "Indian", "Arctic", "Pacific"],
            3),
        ("How many colours are in a rainbow?", ["5", "6", "7", "8"], 2),
        (
            "What is the tallest mountain in the world?",
            ["K2", "Mount Everest", "Kilimanjaro", "Denali"],
            1),
        ("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1),
    ],
    "science": [
        ("What is the chemical symbol for gold?", ["Go", "Gd", "Au", "Ag"], 2),
        (
            "Which gas do plants absorb from the air?",
            ["Oxygen", "Carbon dioxide", "Nitrogen", "Hydrogen"],
            1),
        (
            "What is the powerhouse of the cell?",
            ["Nucleus", "Ribosome", "Mitochondria", "Vacuole"],
            2),
        ("How many bones are in the adult human body?", ["186", "206", "226", "246"], 1),
        (
            "What force keeps planets in orbit around the Sun?",
            ["Magnetism", "Friction", "Gravity", "Inertia"],
            2),
        (
            "What is the most abundant gas in Earth's atmosphere?",
            ["Oxygen", "Carbon dioxide", "Nitrogen", "Argon"],
            2),
    ],
    "geography": [
        (
            "What is the capital of Japan?",
            ["Seoul", "Beijing", "Tokyo", "Bangkok"],
            2),
        (
            "Which country is the largest by land area?",
            ["China", "USA", "Canada", "Russia"],
            3),
        (
            "Which river is the longest in the world?",
            ["Amazon", "Nile", "Yangtze", "Mississippi"],
            1),
        (
            "Which is the largest hot desert?",
            ["Sahara", "Gobi", "Kalahari", "Mojave"],
            0),
        (
            "Which country's flag features a maple leaf?",
            ["Norway", "Canada", "Switzerland", "Denmark"],
            1),
        (
            "What is the capital of Australia?",
            ["Sydney", "Melbourne", "Canberra", "Perth"],
            2),
    ],
    "history": [
        ("In which year did World War II end?", ["1943", "1944", "1945", "1946"], 2),
        (
            "Who was the first person to walk on the Moon?",
            ["Buzz Aldrin", "Yuri Gagarin", "Neil Armstrong", "Michael Collins"],
            2),
        (
            "Which civilisation built the pyramids of Giza?",
            ["Romans", "Greeks", "Egyptians", "Mayans"],
            2),
        (
            "Who painted the Mona Lisa?",
            ["Michelangelo", "Raphael", "Leonardo da Vinci", "Donatello"],
            2),
        (
            "Which wall fell in 1989?",
            ["Hadrian's Wall", "Great Wall", "Berlin Wall", "Wall of Troy"],
            2),
        (
            "Who was the first President of the United States?",
            ["Abraham Lincoln", "George Washington", "Thomas Jefferson", "John Adams"],
            1),
    ],
    "gaming": [
        (
            "Which game features the character Master Chief?",
            ["Halo", "Doom", "Call of Duty", "Destiny"],
            0),
        (
            "Which blocky game lets you mine and craft?",
            ["Roblox", "Terraria", "Minecraft", "Stardew Valley"],
            2),
        (
            "Which company makes the Mario games?",
            ["Sega", "Nintendo", "Sony", "Capcom"],
            1),
        (
            "What is the best-selling video game of all time?",
            ["Tetris", "Minecraft", "GTA V", "Wii Sports"],
            1),
        (
            "In Among Us, who do the crewmates try to eject?",
            ["Crewmates", "Impostors", "Ghosts", "Pets"],
            1),
        (
            "Which Pokémon is number 1 in the Pokédex?",
            ["Pikachu", "Bulbasaur", "Charmander", "Squirtle"],
            1),
    ],
    "movies": [
        (
            "Which film features a ship called the Millennium Falcon?",
            ["Star Trek", "Star Wars", "Firefly", "Guardians of the Galaxy"],
            1),
        (
            "Who directed Jurassic Park?",
            ["James Cameron", "Steven Spielberg", "Ridley Scott", "George Lucas"],
            1),
        (
            "Which animated film features the song 'Let It Go'?",
            ["Moana", "Tangled", "Frozen", "Encanto"],
            2),
        (
            "What is the name of the school in Harry Potter?",
            ["Hogwarts", "Beauxbatons", "Durmstrang", "Ilvermorny"],
            0),
        (
            "Which superhero is known as the Dark Knight?",
            ["Superman", "Batman", "Iron Man", "Spider-Man"],
            1),
        (
            "In Toy Story, what kind of toy is Woody?",
            ["Astronaut", "Cowboy", "Dinosaur", "Soldier"],
            1),
    ],
}

# (word, hint) pairs for hangman.
HANGMAN: list[tuple[str, str]] = [
    ("PYTHON", "a programming language"),
    ("PLANET", "it orbits a star"),
    ("GUITAR", "a musical instrument"),
    ("DRAGON", "a mythical beast"),
    ("PUZZLE", "you solve it"),
    ("TIGER", "a big cat"),
    ("GALAXY", "a huge collection of stars"),
    ("WIZARD", "casts spells"),
    ("COFFEE", "a hot drink"),
    ("RAINBOW", "appears after rain"),
    ("BOTTLE", "holds liquid"),
    ("CASTLE", "a stone fortress"),
    ("PENGUIN", "a flightless bird"),
    ("ROCKET", "flies to space"),
    ("SUNFLOWER", "a tall yellow plant"),
    ("NINJA", "a stealthy warrior"),
    ("DIAMOND", "a precious gem"),
    ("VOLCANO", "erupts with lava"),
    ("LIBRARY", "full of books"),
    ("PUMPKIN", "a big orange gourd"),
    ("SAILOR", "works on a ship"),
    ("MONKEY", "swings through trees"),
    ("WHISPER", "a very quiet voice"),
    ("BLIZZARD", "a heavy snowstorm"),
    ("UNICORN", "a horse with a horn"),
    ("MUSEUM", "displays old things"),
    ("ORCHARD", "grows fruit trees"),
    ("COMPASS", "points north"),
]

# Magic 8-ball answers.
EIGHTBALL: list[str] = [
    "It is certain.",
    "Without a doubt.",
    "Yes — definitely.",
    "Most likely.",
    "Outlook good.",
    "Signs point to yes.",
    "As I see it, yes.",
    "Yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
    "Absolutely not.",
    "The odds are against it.",
]

# (option A, option B) pairs for would-you-rather.
WYR: list[tuple[str, str]] = [
    ("Explore space", "explore the deep sea"),
    ("Always be 10 minutes late", "always be 20 minutes early"),
    ("Have unlimited pizza", "have unlimited tacos"),
    ("Be able to read minds", "be able to turn invisible"),
    ("Give up social media forever", "give up movies forever"),
    ("Fight one horse-sized duck", "fight 100 duck-sized horses"),
    ("Have a pet dragon", "have a pet unicorn"),
    ("Be able to fly", "be able to teleport"),
    ("Live in the mountains", "live on the beach"),
    ("Know the future", "be able to change the past"),
    ("Always speak in rhymes", "always sing instead of talking"),
    ("Have unlimited coffee", "have unlimited tea"),
    ("Be the funniest person alive", "be the smartest person alive"),
    ("Only ever eat sweet food", "only ever eat savoury food"),
    ("Have free Wi-Fi everywhere", "have free food everywhere"),
]

__all__ = ["EIGHTBALL", "HANGMAN", "TRIVIA", "WYR"]
