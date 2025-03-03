#!/usr/bin/env python

# Author: Andrew Jewett (jewett.aij at g mail)
# License: MIT License  (See LICENSE.md)
# Copyright (c) 2020, Scripps Research
# All rights reserved.

man_page_text = """
Usage (example):

postprocess_transitions.py ttree_assignments.txt -t file.template \
    > new_file.template

Where "file.template" contains contents similar to:

if atoms == [@atom:A,@atom:B,@atom:C] and
   bonds == [[1,2], [2,3]] and
   bonding_ids == [1,2] and
   edge_ids == [3]
then
   atoms = [@atom:B,@atom:B,@atom:C] and
   bonds = [[2,3], [3,1]]

Eventually, I will also support this syntax:

if atoms @atom:A @atom:B* @atom:C and 
   bond_type[1,2] == @bond:AB and
   bond_type[2,3] == @bond:BC and
   angle_type[1,2,3] == @angle:ABC and
   distance[1,3] < 3.0 and prob(0.5)
then
   atom_type[2] = @atom:B and
   atom_type[3] = @atom:D and
   delete_bond(1,2) and
   bond_type[1,3] = @bond:AD

if atom_type[1] == @atom:A and 
   atom_type[2] == @atom:B* and
   atom_type[3] == @atom:C and
   bond_type[1,2] == @bond:AB and
   bond_type[2,3] == @bond:BC and
   angle_type[1,2,3] == @angle:ABC and
   distance[1,3] < 3.0 and prob(0.5)
then
   atom_type[2] = @atom:B and
   atom_type[3] = @atom:D and
   delete_bond(1,2) and
   bond_type[1,3] = @bond:AD

if atom_type[1] == @atom:A and 
   atom_type[2] == @atom:B* and
   atom_type[3] == @atom:C and
   bond_type[1,2] == @bond:AB and
   bond_type[2,3] == @bond:BC and
   rmsd((1,2,3), ((1.3,5.2,1.2),(2.4,4.5,6.6),(0.01,1.5,9.55)) <= 3.2
   then
   delete_bond(2,3)
   delete_atom(3)

if atom_type[1] == @atom:A and 
   atom_type[2] == @atom:B* and
   atom_type[3] == @atom:C and
   bond_type[1,2] == @bond:AB and
   bond_type[2,3] == @bond:BC and
   rmsd((1,2,3), ((1.3,5.2,1.2),(2.4,4.5,6.6),(0.01,1.5,9.55)) <= 3.2
then
   coords = ((1.3,5.2,1.2),(2.4,4.5,6.6),(0.01,1.5,9.55),(-1.2,0.1,12)) #add atom
   and atom_type[4] = @atom:D
   and bond_type[3,4] = @bond:CD

"""


# Keywords recognized by this script:
# '[', ']', '(', ')', ',', '==', '=', 'atom_type', 'bond_type', 'angle_type', 'dihedral_type', 'improper_type', 'distance', 'prob', 'rmsd', 'coords', 'delete_atom', 'delete_bond', 'delete_angle', 'delete_dihedral', 'dihedral_improper'
#
# ------ the following features not needed for version 1.0: ------
#
#1) This next step is only needed for rmsd((),())  and coords():
#   Create a variant of SplitQuotedString() that splits according to both
#   parenthesis and commas and works with nested expressions.
#   Call it "SplitNestedQuotes()".  It accepts these arguments with these
#   default values:
#      delim = ','
#      open_paren = '(',
#      close_paren = ')',
#   It will split template lists of this form
#    ['bond((1,2),', VarRef('@/bond:AB'), '), ((2,3),', VarRef('@/bond:BC'),'))']
#        ... which is what ReadTemplate() will return when invoked on
#            'bond(((1,2),@/bond:AB), ((2,3),@/bond:BC))'
#   into something like this:
#        KRUFT ALERT.  THE NEXT FEW LINES OF COMMENTS ARE OUT OF DATE -AJ2020-11
#    ['bond',
#     '(',
#     ['(1,2),', VarRef('@/bond:AB')],
#     ['(2,3),', VarRef('@/bond:BC')],
#     ')']
#   Note: This function only processes the outermost paren expression.
#         The '(1,2),' was not processed further.  Had it been, it would have
#         returned [['(', ['1','2'] ,')'], '']
#   
#2) Use SplitNestedQuotes() to find the arguments following the
#   rmsd() and coords() keywords.

import sys
import argparse
from collections import defaultdict
import re
import gc

try:
    from .ttree import ExtractFormattingCommands
    from .ttree_lex import *

except (ImportError, SystemError, ValueError):
    # not installed as a package
    from ttree import ExtractFormattingCommands
    from ttree_lex import *


g_filename = __file__.split('/')[-1]
g_module_name = g_filename
if g_filename.rfind('.py') != -1:
    g_module_name = g_filename[:g_filename.rfind('.py')]
g_date_str = '2020-11-04'
g_version_str = '0.0.3'
g_program_name = g_filename
#sys.stderr.write(g_program_name+' v'+g_version_str+' '+g_date_str+' ')





def main():
    try:
        ap = argparse.ArgumentParser(prog=g_program_name)
        ap.add_argument('bindings_filename',  # (positional argument)
                        help='assignments file name (usually "ttree_assignments.txt")')
        ap.add_argument('-t', '--template', dest='template', required=False,
                        help='template text file (typically generated by moltemplate, and ending in ".template")')
        args = ap.parse_args()
        bindings_filename = args.bindings_filename
        f = open(bindings_filename)

        atom_types = set([])
        bond_types = set([])
        angle_types = set([])
        dihedral_types = set([])
        improper_types = set([])

        # The line above is robust but it uses far too much memory.
        # This for loop below works for most cases.
        for line in f:
            #tokens = lines.strip().split()
            # like split but handles quotes
            tokens = SplitQuotedString(line.strip())
            if len(tokens) < 2:
                continue
            if tokens[0].find('@') != 0:
                continue
            if tokens[0][2:].find('atom') == 0:
                atom_types.add(tokens[0][1:])
            elif tokens[0][2:].find('bond') == 0:
                bond_types.add(tokens[0][1:])
            elif tokens[0][2:].find('angle') == 0:
                angle_types.add(tokens[0][1:])
            elif tokens[0][2:].find('dihedral') == 0:
                dihedral_types.add(tokens[0][1:])
            elif tokens[0][2:].find('improper') == 0:
                improper_types.add(tokens[0][1:])

        f.close()
        gc.collect()


        # Now open the template file containing the list of transition rules.

        if args.template is not None:
            templ_file = open(args.template, 'r')
            lex = LineLex(templ_file)
        else:
            templ_file = sys.stdin
            lex = TtreeShlex(sys.stdin,
                             '__standard_input_for_postprocess_coeffs__')
        lex.commenters = '#'           #(don't attempt to skip over comments)
        lex.line_extend_chars += '&'   #(because LAMMPS interprets '&' as '\')

        transition_rules_orig = []
        if_clause = []
        then_clause = []
        in_if_clause = True
        while lex:
            token = lex.get_token()
            if ((token == '') or (token == 'if')):
                if ((len(if_clause)>0) and (len(then_clause)>0)):
                    transition_rules_orig.append([if_clause, then_clause])
                    if_clause = []
                    then_clause = []
                if token == 'if':
                    in_if_clause = True
                    continue
                elif token == '':
                    break
            elif token == 'then':
                then_clause = []
                in_if_clause = False
                continue
            elif token in ('@', '$'):
                var_name = GetVarName(lex)
                token = token + var_name  # for example: "@/atom:GAFF2/c3"
            if in_if_clause:
                if_clause.append(token)
            else:
                then_clause.append(token)

        # now close the file (if we opened it)
        if args.template is not None:
            templ_file.close()

        # Now split the if and then clauses into tokens separated by "and"
        if_requirements = []
        if_requirement = []
        then_results = []
        then_result = []
        for rule in transition_rules_orig:
            if_clause = rule[0]
            then_clause = rule[1]
            #split the if_clause into lists of tokens separated by 'and':
            for token in if_clause:
                if ((token == 'and') and (len(if_requirement) > 0)):
                    if_requirements.append(if_requirement)
                    if_requirement = []
                else:
                    if_requirement.append(token)
            if len(if_requirement) > 0:
                if_requirements.append(if_requirement)
            # Replace rule[0] with the if_requirements list
            rule[0] = if_requirements

            #split the then_clause into lists of tokens separated by 'and'
            for token in then_clause:
                if ((token == 'and') and (len(then_result) > 0)):
                    then_results.append(then_result)
                    then_result = []
                else:
                    then_result.append(token)
            if len(then_result) > 0:
                then_results.append(then_result)
            # Replace rule[1] with the then_results list
            rule[1] = then_results


        # Now loop through all of the transition rules.  For each rule,
        # figure out how many times the user specified an atom type, or
        # bonded type, or angle type or dihedral type or improper type
        # which must be satisfied in order to satisfy the if conditions.
        #
        # Then, for that rule, generate a separate transition rule for
        # every possible combination of atom types, bond types, angle types,
        # dihedral types, and improper types which satisfies the requirements
        # specified by the user after considering wildcards and regex.
        # In this way, a single rule specified by the user (with vague atom
        # type names or vague bonded type napes) might get translated
        # (expanded) into a large number of individual transition rules
        # for use with fix bond/react, where in each rule, each atom type,
        # bond type, angle type, etc... is specified explicitly.

        Natoms = 0 # we will store the number of atoms in the
                   # pre-reaction template here
        transition_rules = [] # we will store processed transition rules here
        atom_req = []  # atom type requirements
        bond_req = []  # bond type requirements
        angle_req = []  # angle type requirements
        dihedral_req = []  # dihedral type requirements
        improper_req = []  # improper type requirements
        for rule in transition_rules_orig:
            if_requirements = rule[0]
            for if_requirement in if_requirements:
                tokens = if_requirement
                assert(len(tokens) > 0)
                iatm = -1
                if tokens[0] == 'atom':
                    # allow users to use either '=' or '==' to test for equality
                    # For example, these should both work:
                    #    'if atom[1] == @atom:A'
                    #    'if atom[1] = @atom:A'.
                    # But if '==' was used, the lexer will mistake this for
                    # two separate tokens ('=' followed by '=').  We take care
                    # of that here by deleting the extra '='
                    if (tokens[4] == tokens[5] == '='):
                        tokens[4] = '=='
                        del tokens[5]
                    if not ((len(tokens) == 6) and
                            (tokens[1] == '[') and
                            (tokens[2].isnumeric() and
                             (int(tokens[2]) > 0)) and
                            (tokens[3] == ']') and
                            (tokens[4] == '==') and
                            ((tokens[5].find('@') != -1) and
                             (tokens[5].find('atom:') != -1))):
                        raise InputError('Error in transitions file near:\n'+
                                         '      '+' '.join(tokens)+'\n')

                iatm = int(tokens[2])
                if iatm >= Natoms:
                    atom_req += [[] for i in range(0, 1 + iatm - Natoms)]
                    Natoms = iatm + 1
                    assert(Natoms == len(atom_req))

                typestr = tokens[5][1:]  # a string identifying atom type(s)
                                         # eg: '@atom:/SPCE/O' or '@atom:C*'
                #icolon = typestr.find('atom:') + 5
                #typestr = typestr[icolon:]

                # If the second token is surrounded by '/' characters, interpret
                # it as a regular expression.
                type_is_re = HasRE(typestr)

                # If the second token contains wildcard characters, interpret
                # it as a wildcard (ie. glob) expression.
                type_is_wild = (HasWildcard(typestr) #does it contain *,?
                                and
                                (typestr[0] != '{')) #(ignore * or ? in {})

                if type_is_re:
                    regex_str = VarNameToRegex(typestr)
                    typepattern = re.compile(regex_str)
                else:
                    #left_paren, typepattern, text_after=ExtractVarName(typestr)
                    typepattern = typestr
                    left_paren = ''
                    text_after = ''
                for atype in atom_types:
                    if MatchesPattern(atype, typepattern):
                        #atom_req[iatm].append('@'+left_paren+atype+text_after)
                        atom_req[iatm].append('@{'+atype+'}')

        # ------------------ CONTINUEHERE --------------------
                    


    except (ValueError, InputError) as err:
        sys.stderr.write('\n' + str(err) + '\n')
        sys.exit(-1)

    return

if __name__ == '__main__':
    main()
