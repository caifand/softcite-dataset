"""Constructs data set."""

import rdflib
from rdflib import URIRef, Literal
from rdflib.namespace import RDF
import pprint
import sys
import glob
import getopt
import os
import subprocess
import re
import logging
import progressbar

# class Error(Exception):
#     """Base class for exceptions in this module."""
#     pass
#
# class FormatError(Error):
#     """Exception raised for errors in the input.
#
#     Attributes:
#         expression -- input expression in which the error occurred
#         message -- explanation of the error
#     """
#
#     def __init__(self, message):
#     #    self.expression = expression
#         self.message = message


def find_all_turtle_files(dir_to_check = "data"):
    files = []
    files += glob.glob(dir_to_check + "*.ttl")
    # Add individuals
    files.extend(glob.glob(dir_to_check + "/individuals-**/*.ttl"))

    # remove demo files
    regex = re.compile(r'demo|practice|sample|test|jameshowison')
    files = [i for i in files if not regex.search(i)]

    return files

def parse_individual_file(file_to_check):
    g = rdflib.Graph()
    result = g.parse(file_to_check, format="n3")
    msg = "{} has {} statements."
    print(msg.format(file_to_check, len(g)))
    return result

def parse_each_file(files):
    for file_to_check in files:
        parse_individual_file(file_to_check)


def validate_file(file_to_check):
    """A valid file passes these checks.

    1. Parses as RDF
    2. Selections URIs all match
    """
    file_graph = rdflib.Graph()
    file_graph.parse(file_to_check, format="n3")

    try:
        check_selections_in_body(file_graph, file_to_check)
    except Exception as err:
        logging.warning("Formatting issue: {}".format(str(err)))
        # raise


# def check_article_url(file_graph):
#     article_url = URIRef(u'http://james.howison.name/ontologies/bio-journal-sample#article')
#     print("Checking article URL")
#     article_statements = file_graph.subjects(RDF.type,
#                                           article_url)
#
#
#     for art in article_statements:
#         print(art)
#
#     return file_graph


def check_selections_in_body(file_graph, file_to_check):
    selections_in_header = file_graph.objects( predicate =  URIRef(u'http://james.howison.name/ontologies/software-citation-coding#has_in_text_mention'))

    for sel in selections_in_header:
        if sel:
            if (sel,
                RDF.type, URIRef(u'http://james.howison.name/ontologies/software-citation-coding#in_text_mention')) not in file_graph:
                raise Exception("Parsing {} \nMissing Body: Did not find {}".format(file_to_check, sel))

    # Now the other way around. Checking that all in_text_mentions are in header.
    # finding pmcid:PMC5226643_JWC01 rdf:type citec:in_text_mention
    # looking for citec:has_in_text_mention pmcid:PMC5226643_JWC01
    selections_in_body = file_graph.subjects(object=URIRef(u'http://james.howison.name/ontologies/software-citation-coding#in_text_mention'))

    for sel in selections_in_body:
        if sel:
            if ( None,
                URIRef(u'http://james.howison.name/ontologies/software-citation-coding#has_in_text_mention'),
                sel
                ) not in file_graph:
                raise Exception("Parsing {} \nMissing header: Did not find {}".format(file_to_check, sel))

    return file_graph


def build_parse_data_set(dir_to_check="data"):

    files = find_all_turtle_files(dir_to_check)
    while "data/full_dataset.ttl" in files:
        files.remove("data/full_dataset.ttl")

    all_files = rdflib.Graph()

    for file_to_check in progressbar.progressbar(files):
        # print("Validating {}".format(file_to_check))
        # validate_file(file_to_check)
        # print("Parsing {}".format(file_to_check))
        all_files.parse(file_to_check, format="n3")

    pmc_articles = all_files.query("""
    CONSTRUCT { ?article rdf:type bioj:pmc_article }
    WHERE {
      ?article rdf:type bioj:article .
      FILTER regex(str(?article), "PMC")
    }""")

    pmc_articles.serialize(
      destination="data/pmc_article_statements.ttl",
      format="turtle"
    )

    all_files.parse("data/pmc_article_statements.ttl", format="turtle")

    training_articles = all_files.query("""
    CONSTRUCT { ?article rdf:type bioj:training_article }
    WHERE {
      ?article rdf:type bioj:article .
      FILTER regex(str(?article), "bio-journal-sample.a")
    }""")

    training_articles.serialize(
      destination="data/article_training_statements.ttl",
      format="turtle"
    )

    all_files.parse("data/article_training_statements.ttl", format="turtle")

    return all_files


def extract_assignments_csv():
    import pymysql
    import csv

    print('Outputting assignments csv')
    connection = pymysql.connect(host="localhost",
                                 user="softcite_user",
                                 passwd="work_spree34",
                                 db="softcite_assignments",
                                 autocommit=True,
                                 cursorclass=pymysql.cursors.DictCursor)

    cursor = connection.cursor()

    sql_query = """
        SELECT *
        FROM assignments
    """
    cursor.execute(sql_query)
    headers = ["id", "pub_id", "assigned",
               "assigned_to", "asssigned_timestamp"]
    with open('data/softcite_assignments.csv', 'w') as csvfile:
        myCsvWriter = csv.DictWriter(csvfile, fieldnames=headers)
        myCsvWriter.writeheader()
        for row in cursor:
            # rather than 'for row in results'
            myCsvWriter.writerow(row)


def usage():
    print("-a <directory> to parse all files, -f <filename> for just one file")


def main(argv):
    grammar = "kant.xml"
    try:
        opts, args = getopt.getopt(argv, "uca:f:", ["help", "grammar="])
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)

    for o, a in opts:
        if o == "-a":
            full_dataset = build_parse_data_set(a)
            full_dataset.serialize(
              destination="data/full_dataset.ttl",
              format="turtle"
            )
            output = subprocess.check_output([
            'sh',
            'shacl-1.1.0/bin/shaclvalidate.sh',
            '-shapesfile',
            'data/softcite_shacl_constraints.ttl',
            '-datafile',
            'data/full_dataset.ttl'])

            output_graph = rdflib.Graph()
            output_graph.parse(data=output, format="n3")
            if (None,
                URIRef(u'http://www.w3.org/ns/shacl#conforms'),
                Literal(False)) in output_graph:
                logging.warning("SHACL issue: {}".format(output))
                print("Validation warning, check log file")
            extract_assignments_csv()
        elif o == "-c":
            extract_assignments_csv()
        elif o == "-u":
            reply = subprocess.check_output(
                    ["curl",   'https://api.data.world/v0/uploads/jameshowison/software-citations/files/full_dataset.ttl',
                    "--upload-file", "data/full_dataset.ttl",
                    "-H",
                    "Authorization: Bearer {}".format(os.environ['DATA_WORLD_KEY'])
                    ]
            ).decode("utf8")
            print(reply)
            reply = subprocess.check_output(
                    ["curl",   'https://api.data.world/v0/uploads/jameshowison/software-citations/files/softcite_assignments.csv',
                    "--upload-file", "data/softcite_assignments.csv",
                    "-H",
                    "Authorization: Bearer {}".format(os.environ['DATA_WORLD_KEY'])
                    ]
            ).decode("utf8")
            print(reply)
        elif o == "-f":
            validate_file(a)
        else:
            assert False, "unhandled option"


if __name__ == '__main__':
    progressbar.streams.wrap_stderr()
    logging.basicConfig(filename='parseTurtle.log',
                        filemode="w",
                        level=logging.WARN)
    logging.warning("Logging enabled")

    main(sys.argv[1:])


# sparql_query = """
# SELECT ?grant ?code ?value ?url
# WHERE {
#    ?grant_node rdf:type vivo:grant ;
#                rdfs:label ?grant ;
#              ca:isTargetOf ?ca .
#    ?ca ca:appliesCode ?codeNode .
#    ?codeNode rdf:type ?code .
#    OPTIONAL { ?codeNode transition:isPresent ?value ;
#                          transition:hasURL ?url }
#       }
# """

# sparql_query = """
# SELECT ?grant ?code ?value ?url
# WHERE {
#    ?grant_node rdf:type vivo:grant ;
#                rdfs:label ?grant ;
#              ca:isTargetOf ?ca .
#    ?ca ca:appliesCode [ rdf:type ?code ]
#                         transition:isPresent ?value ;
#                         transition:hasURL ?url ]
#           }
# """# rowDict = {}
 #  rowDict["grant"] = row.grant.n3(g.namespace_manager)
 #  rowDict["code"] = row.code.n3(g.namespace_manager)
 #  rowDict["value"] = row.value.n3(g.namespace_manager)
 #  rowDict["url"] = row.url.n3(g.namespace_manager)
 #  #pprint.pprint(rowDict)
 #  print("{grant},{code},{value},{url}".format(**rowDict))

########
# Full list of codes used.
########

# sparql_query = """
# SELECT DISTINCT ?code
# WHERE {
#    ?ca ca:appliesCode ?codeNode .
#    ?codeNode rdf:type ?code .
#       }
# """
#
# qres = g.query(sparql_query)
#
# for row in qres:
#   print("{} rdf:type transition:ContentAnalysisCode .".format(row.code.n3(g.namespace_manager)))
#
# g = rdflib.Graph()
# result = g.parse("../data/coding-scheme.ttl", format="n3")
#
# print("coding scheme graph has {} statements.".format(len(g)))
#
# sparql_query = """
# SELECT DISTINCT ?code
# WHERE {
#    ?ca ca:appliesCode ?codeNode .
#    ?codeNode rdf:type ?code .
#       }
# """
#
# qres = g.query(sparql_query)
#
# for row in qres:
#   print("{} rdf:type transition:ContentAnalysisCode .".format(row.code.n3(g.namespace_manager)))
