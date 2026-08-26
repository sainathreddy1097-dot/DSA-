def edit_distance(s1, s2):
    """
    Computes the Edit Distance (Levenshtein distance) between two strings
    using the Wagner-Fischer dynamic programming algorithm.
    """
    m = len(s1)
    n = len(s2)

    # Initialize DP table of size (m+1) x (n+1)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Fill base cases: converting prefix of s1 to empty string requires deletions
    for i in range(m + 1):
        dp[i][0] = i

    # Fill base cases: converting empty string to prefix of s2 requires insertions
    for j in range(n + 1):
        dp[0][j] = j

    # Compute minimum operations for all subproblems
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                cost = 0
            else:
                cost = 1

            dp[i][j] = min(
                dp[i - 1][j] + 1,       # Deletion
                dp[i][j - 1] + 1,       # Insertion
                dp[i - 1][j - 1] + cost  # Replacement
            )

    return dp[m][n]


import os


if __name__ == "__main__":
    # Open and read dictionary words (relative to script directory)
    file_path = os.path.join(os.path.dirname(__file__), "words.txt")
    with open(file_path, "r") as file:
        words = file.read().splitlines()

    query = input("Enter search word: ")

    print("\nSimilar Words")
    print("----------------")

    for word in words:
        distance = edit_distance(query.strip(), word)
        if distance <= 3:
            print(f"{word}  Edit Distance = {distance}")
