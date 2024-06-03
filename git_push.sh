#!/bin/bash

# Get current git username and email
current_username=$(git config user.name)
current_email=$(git config user.email)

# Echo current git username and email to the user
echo "Current Git username: $current_username"
echo "Current Git email: $current_email"

# Ask the user what they want to add
read -p "What do you want to add to the commit? (default is '.') : " add_target
add_target=${add_target:-"."}

# Perform git add
git add $add_target

# Ask for commit message
read -p "Enter commit message: " commit_message

# Perform git commit
git commit -m "$commit_message"

# Confirm what will be pushed
echo "The following changes will be pushed:"
git status

read -p "Do you want to push these changes? (yes/y to confirm) : " confirm_push
confirm_push=${confirm_push,,} # convert to lowercase

if [[ $confirm_push == y* ]]; then
    # Push to GitHub
    echo "Pushing to GitHub..."
    git push origin main
    echo "GitHub push complete."

    # Push to Azure DevOps
    echo "Pushing to Azure DevOps..."
    git push azure main
    echo "Azure DevOps push complete."
else
    echo "Push aborted."
fi

exit 0

