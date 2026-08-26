# ==============================================================================
# Practical 6: Implementation of Sequence Alignment and Bitmask Dynamic
#              Programming for Optimization Problems
# Course Outcome: CO3
# Aim: To implement Sequence Alignment using DP and solve optimization using
#      Bitmask Dynamic Programming.
# ==============================================================================

# Part A: Sequence Alignment using Dynamic Programming
def sequence_alignment(seq1, seq2):
    # Get the lengths of both sequences
    m = len(seq1)
    n = len(seq2)

    # Create the Dynamic Programming table
    dp = [[0 for j in range(n + 1)] for i in range(m + 1)]

    # Initialize the first column with gap penalties
    for i in range(m + 1):
        dp[i][0] = -i

    # Initialize the first row with gap penalties
    for j in range(n + 1):
        dp[0][j] = -j

    # Fill the DP table
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # Match gets +1 and mismatch gets -1
            if seq1[i - 1] == seq2[j - 1]:
                score = 1
            else:
                score = -1

            # Choose the best score:
            # Diagonal = match or mismatch
            # Up = gap in sequence 2
            # Left = gap in sequence 1
            dp[i][j] = max(
                dp[i - 1][j - 1] + score,
                dp[i - 1][j] - 1,
                dp[i][j - 1] - 1
            )

    # Return the optimal alignment score
    return dp[m][n]


print("--- Part A: Sequence Alignment ---")
# Get sequences from the user
seq1 = input("Enter Sequence 1: ")
seq2 = input("Enter Sequence 2: ")

# Calculate and display alignment score
result = sequence_alignment(seq1, seq2)
print("Optimal Alignment Score =", result)


print("\n--- Part B: Bitmask Dynamic Programming for Optimization ---")
# Bitmask Dynamic Programming for subset optimization
values = [10, 20, 30, 40]
max_items = 2
n = len(values)
best_value = 0
best_subset = []

# A mask represents a subset of items
# Example: 0101 means select item 0 and item 2
for mask in range(1 << n):
    total = 0
    selected = []

    # Check every bit of the mask
    for i in range(n):
        # If the i-th bit is 1, select that item
        if mask & (1 << i):
            total += values[i]
            selected.append(values[i])

    # Update the best solution
    if len(selected) <= max_items and total > best_value:
        best_value = total
        best_subset = selected

print("Maximum number of items =", max_items)
print("Best selected items =", best_subset)
print("Maximum value =", best_value)
