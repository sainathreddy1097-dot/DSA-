# ==============================================================================
# Practical 5: Implementation of Edit Distance Computation and Fuzzy Search
#              using Wagner–Fischer Algorithm
# Course Outcome: CO3
# Aim: To compute Edit Distance between two strings and perform Fuzzy Search.
# ==============================================================================

import os


# Function to calculate Edit Distance using Wagner-Fischer Algorithm
def edit_distance(s1, s2):
    # Find the length of both strings
    m = len(s1)
    n = len(s2)

    # Create a Dynamic Programming table of size (m+1) x (n+1)
    dp = [[0 for j in range(n + 1)] for i in range(m + 1)]

    # Initialize the first column
    # Number of deletions needed to convert s1 into an empty string
    for i in range(m + 1):
        dp[i][0] = i

    # Initialize the first row
    # Number of insertions needed to convert an empty string into s2
    for j in range(n + 1):
        dp[0][j] = j

    # Fill the Dynamic Programming table
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # If characters are the same, no operation is needed
            if s1[i - 1] == s2[j - 1]:
                cost = 0
            else:
                # If characters are different, replacement costs 1
                cost = 1

            # Choose the minimum cost among deletion, insertion, and replacement
            dp[i][j] = min(
                dp[i - 1][j] + 1,        # Deletion
                dp[i][j - 1] + 1,        # Insertion
                dp[i - 1][j - 1] + cost  # Replacement
            )

    # Return the final minimum Edit Distance
    return dp[m][n]


# Read words from the text file
script_dir = os.path.dirname(os.path.abspath(__file__))
words_path = os.path.join(script_dir, "words.txt")

with open(words_path, "r") as file:
    words = file.read().splitlines()

# Take the search word from the user
query = input("Enter search word: ")

print("\nSimilar Words")
print("----------------")

# Compare the search word with every word in words.txt
for word in words:
    # Calculate the Edit Distance
    distance = edit_distance(query.lower(), word.lower())
    # Display words with Edit Distance less than or equal to 3
    if distance <= 3:
        print(word, "Edit Distance =", distance)
