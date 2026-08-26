import os

script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "problems.txt")

with open(file_path, "r") as file:
    problems = file.readlines()

print("Problem Mapping\n")

for problem in problems:

    problem = problem.strip()

    print("Problem :", problem)

    if "Search" in problem:
        print("Algorithm : String Matching")

    elif "Sort" in problem:
        print("Algorithm : Sorting")

    elif "shortest" in problem.lower():
        print("Algorithm : Graph Algorithm")

    elif "duplicate" in problem.lower():
        print("Algorithm : Document Similarity")

    elif "Sudoku" in problem:
        print("Algorithm : Backtracking")

    elif "Compress" in problem:
        print("Algorithm : Greedy")

    print("-----------------------------")
