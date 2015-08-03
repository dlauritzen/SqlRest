# SQLRest

A super-thin wrapper around MySQL.

# Disclaimer

Allowing this kind of access to your database from the outside world is a dangerous thing. The safety and
privacy of your server and data is your responsibility.

# Authorization

All requests require authentication.

Users authenticate to the MySQL server by passing up credentials using
HTTP basic authentication. To protect the user and the server, all requests
should require HTTPS.

The root user is not allowed.

# config.ini

All configuration options are loaded from the config.ini file located in the same
directory as settings.py.

# URL Structure

For most requests, the URL contains all the information necessary to construct the query.

> {Base Url}/{Database}/{Table}/{ID}

## Base Url

The config.ini file contains a setting for "base" url. This is the url prefix at which
Django passes control over to the API.

## Database

This part of the url determines which database to connect to.

## Table

This part of the url determines which table to execute the query on.

## ID

This part of the url determines which record to retrieve or update. If no ID is provided, all
records in the table are selected (unless "where" clauses are provided).

## Commands

Instead of providing a database, table, or ID, some commands can be executed. All commands are
prefixed by '\_', and the server considers any portion of the url beginning with that prefix to
be a command. This prefix can be changed in config.ini under COMMAND_PREFIX.

Any query parameter prefixed by '\_' in this documentation also is affected by the COMMAND_PREFIX
setting, so changing it will also change the prefix for those parameters.

### Show Databases

> {Base Url}/\_databases

This command lists all databases the authenticated user may select.

### Show Tables

> {Base Url}/{Database}/\_tables

This command lists all tables in the selected database.

### Describe Table

> {Base Url}/{Database}/{Table}/\_describe

This command lists information about each column in the selected table.

# Where Clauses

Url query parameters may be used in some queries to act as "where" clauses and limit the query results.

The parameter format is modelled after Django's QuerySet field lookup format. See the Django documentation
for details. All the lookups are supported except for range, search, regex, and ones related to date (year, month, etc).

When using an "in" or "notin" clause, provide the list of values in JSON or by repeating the query parameter key.

# Order, Limit, and Offset

Adding \_limit, \_offset, and \_order (or \_order\_desc) query parameters to a select statement appends the respective
command to the end of the query. Limit and offset must be integers, obviously.

The \_order and \_order\_desc parameters take the column name as their value. \_order uses ascending (A-Z) order,
while \_order\_desc uses descending (Z-A) order.

# Raw Queries

In case of complex queries not covered elsewhere in the API, it is possible to pass up a raw query
to the server which is run, unmodified. Make a POST request to

> {Base Url}/{Database}/\_query

with the query as the post body.

DELETE and DROP queries are disallowed, as is executing multiple queries in a single request.
Since my code for detecting multiple queries is very simple, any semicolon not at the end or beginning
of the query is treated as separating multiple queries, even if it is contained in a string.

# License

![Public Domain](http://i.creativecommons.org/p/zero/1.0/88x31.png)

To the extent possible under law, [Dallin Lauritzen](http://dallinlauritzen.com) as waived all copyright
and related or neighboring rights to SqlRest. This work is published from: United States.

In other words, I release this code into the [Public Domain](http://creativecommons.org/publicdomain/zero/1.0/).

