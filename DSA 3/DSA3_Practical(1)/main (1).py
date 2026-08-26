# ==============================================================================
# Practical 1: Corpus Loading and Article Repository Creation for TextHack
# Course Outcome: CO1
# Aim: To create an article repository and load articles into the TextHack system.
# ==============================================================================

import os

# Open the article repository using script relative path
script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "articles.txt")

with open(file_path, "r") as file:
    # Read all articles from the file
    articles = file.read()

# Display heading
print("TEXTHACK ARTICLE REPOSITORY")
print("----------------------------------")
# Display all articles
print(articles)
