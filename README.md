## countpy: Python Package Metrics

Developers of open-source Python packages sometimes envy R developers for the simple perks they enjoy, like a reliable web service that gives a reasonable count of the total number of times an R package has been downloaded. To achieve the same, Python developers must launch a Google Query and wait for generally 30 or so seconds. 

Then there are sore spots that are shared by both R and Python developers. Downloads are a shallow metric. Developers often want to know how often people writing Python scripts and packages use their package. We partly solve this latter problem for Python developers by pooling search results from Github.  And in doing so, give them one reasonable lower bound of the closest proxy to a citation in software---proof that people used a piece of software to do something.

[countpy.com](http://countpy.com) provides the number of times a package has been called in the requirements file, and how often it has been imported. 

We leverage the Github search API to achieve this.

### Functionality

http://countpy.com supports two functions:

1. Search: Get information on imports, etc. for any Python package.

2. Badge: To get a badge for the total number of imports etc. in Github, try http://countpy.com/badge/numpy

### Outline of the Application

1. **Searching GitHub:** The script [searchpy.py](searchpy.py) uses the GitHub search API to search all .py files for all `import` statements. The script can spawn multiple processes that use different GitHub credentials, all of which are stored in config.txt. Currently, the default is 2. The script respects Github Search API's limits. The meta logic of the limits is also stored in the config file to allow for easy change if Github changes. The script writes to a JSON file called `search_results_start_date.json`. The JSON file has the following fields: 
    * package_name: name of the package
    * repository_name: name of the repo. that has files that import the package
    * n_files_in_repo_that_import_package: total number of files in the repo. that import the package
    * requirements_file_mentions_package_name: 0/1
    * version_of_package: version of the package if you can get it from requirements file.
    * search_date: date the repo. was searched

    The script also gzips the final JSON file and stores it in `data/search_results_start_date.json.gzip`.

2. **UI:** The UI is minimal. It provides a large search box in which you can search for the package. The search results lists all exact matches and any approximate matches (edit distance of 2). And if you click on the package name, it shows you a table:
       
       ```
       package, number of repositories importing, number of files, number of requirements files, date
       ```

### Code Organization

* [config file]() stores some key variables like database credentials and things to do with how the service looks.

## Authors

Gaurav Sood and Khanh Tran
