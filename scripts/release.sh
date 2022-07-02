#!/bin/sh -x
DIRNAME="$(dirname "$0")"

# set PROJECT_NAME variable
. "$DIRNAME"/projectname.sh

# utility functions
. "$DIRNAME"/functions.sh

if ! branch_is_main;
then
    quit "Checkout branch 'main' before generating release." 1
fi

if ! branch_is_clean;
then
    echo "Tree contains uncommitted modifications:"
    git ls-files -m
    quit 1
fi
version=$(current_version);

if ! version_is_tagged "$version";
then
    echo "Current version $version isn't tagged."
    echo "Attempting to tag..."
    "$DIRNAME"/tag.sh || quit "Failed to tag a release." 1
fi

generate_dist(){
    python3 setup.py sdist bdist_wheel || quit "Failed to generate source & binary distributions." 1
}

version=$(current_version);

# generate_dist;
# echo "About to post the following distribution files to pypi.org."
# ls -1 dist/"$PROJECT_NAME"-"$version".* || quit "No distribution files found." 1

# if prompt_yes_no;
# then
#     python3 -m twine upload dist/"$PROJECT_NAME"-"$version"*
# fi
