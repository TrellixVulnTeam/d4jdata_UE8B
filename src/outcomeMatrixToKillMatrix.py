"""Turn a test-outcome matrix into a killage matrix, indicating which tests kill which mutants.

Usage:

    outcome-matrix-to-kill-matrix \
      --error-partition-scheme SCHEME \
      --outcomes FILE \
      --mutants FILE \
      --output FILE

where SCHEME is one of:

- `passfail' (all exceptions are equivalent to each other and to timeouts/crashes)
- `all` (all exceptions are equivalent)
- `type` (exceptions of the same type are equivalent)
- `type+message` (exceptions with the same type and message are equivalent)
- `type+message+location` (exceptions with the same type, message, and location are equivalent)
- `exact` (exceptions that have exactly the same stack trace are equivalent)

and `--mutants` points to a "mutants.log" file produced by Major.
"""

import gzip
import collections
import re
import argparse
import itertools

PASS = 'PASS'
FAIL = 'FAIL'

def distill_type(trace):
  m = re.match(r'[\w.$]+', trace)
  return (m.group() if m else trace)

def distill_type_message(trace):
  m = re.match(r'(?P<first_line>.*?) at [\w.$]+\([^)]*\.java:\d+\)', trace)
  return (m.group('first_line') if m else trace)

def distill_type_message_location(trace):
  m = re.match(r'(?P<first_line>.*?) at (?P<location>[\w.$]+\([^)]*\.java:\d+\))', trace)
  return (m.group('first_line', 'location') if m else trace)

STACK_TRACE_DISTILLING_FUNCTIONS = {
  'all': (lambda trace: ''),
  'type': distill_type,
  'type+message': distill_type_message,
  'type+message+location': distill_type_message,
  'exact': (lambda trace: trace)
}
ERROR_PARTITION_SCHEMES = set(STACK_TRACE_DISTILLING_FUNCTIONS.keys())
ERROR_PARTITION_SCHEMES.add('passfail')

Outcome = collections.namedtuple(
  'Outcome',
  ('test_case', 'mutant_id', 'timeout',
   'category', 'runtime', 'output_hash', 'covered_mutants', 'stack_trace'))

def parse_outcome_line(line):
  result = Outcome(*line.split(',', 7))
  return result._replace(
    mutant_id=int(result.mutant_id),
    timeout=int(result.timeout),
    runtime=int(result.runtime),
    covered_mutants=(set(int(n) for n in result.covered_mutants.split(' ')) if result.covered_mutants else set()))

def are_outcomes_equivalent(outcome1, outcome2, error_partition_scheme):
  if error_partition_scheme == 'passfail':
    return (outcome1.category=='PASS') == (outcome2.category=='PASS')
  if outcome1.category == outcome2.category == FAIL:
    key = STACK_TRACE_DISTILLING_FUNCTIONS[error_partition_scheme]
    return key(outcome1.stack_trace) == key(outcome2.stack_trace)
  else:
    return outcome1.category == outcome2.category

def find_killed_mutants(original_outcome, mutated_outcomes, error_partition_scheme):
  return set(
    outcome.mutant_id for outcome in mutated_outcomes
    if not are_outcomes_equivalent(outcome, original_outcome, error_partition_scheme))

def format_kill_matrix_row(killed_mutants, n_mutants, originally_passing):
  words = ['1' if i in killed_mutants else '0' for i in range(1, n_mutants+1)]
  words.append('+' if originally_passing else '-')
  return ' '.join(words)

def group_outcomes_by_test_case(outcomes):
  for _test_case, group in itertools.groupby(outcomes, key=(lambda outcome: outcome.test_case)):
    original_outcome = next(group)
    if original_outcome.mutant_id != 0:
      raise ValueError('expected first outcome for test case to be have mutant_id 0, but was not: {}'.format(original_outcome))
    yield (original_outcome, group)

def count_mutants(mutants_file):
  return max(
    int(match.group()) for match in (
      re.match(r'\d+(?=:)', line) for line in mutants_file)
    if match)

def open_killmap(path):
  return gzip.open(path) if path.endswith('.gz') else open(path)

def genKillage(error_partition_scheme, outcomes, mutants, output):

  with open(mutants) as mutants_file:
    n_mutants = count_mutants(mutants_file)

  with open_killmap(outcomes) as outcome_matrix_file, open(output, 'w') as output_file:
    all_outcomes = (parse_outcome_line(line) for line in outcome_matrix_file)
    for original_outcome, mutated_outcomes in group_outcomes_by_test_case(all_outcomes):
      killed_mutants = find_killed_mutants(original_outcome, mutated_outcomes, error_partition_scheme)
      output_file.write(format_kill_matrix_row(killed_mutants, n_mutants, original_outcome.category==PASS))
      output_file.write('\n')

if __name__ == '__main__':

  import argparse
  import itertools

  parser = argparse.ArgumentParser()
  parser.add_argument('--error-partition-scheme', required=True, choices=ERROR_PARTITION_SCHEMES)
  parser.add_argument('--outcomes', required=True, help='path to the outcome matrix produced by Killmap')
  parser.add_argument('--mutants', required=True, help='path to a Major mutants.log file')
  parser.add_argument('--output', required=True, help='file to write output matrix to')

  args = parser.parse_args()

  with open(args.mutants) as mutants_file:
    n_mutants = count_mutants(mutants_file)

  with open_killmap(args.outcomes) as outcome_matrix_file, open(args.output, 'w') as output_file:
    all_outcomes = (parse_outcome_line(line) for line in outcome_matrix_file)
    for original_outcome, mutated_outcomes in group_outcomes_by_test_case(all_outcomes):
      killed_mutants = find_killed_mutants(original_outcome, mutated_outcomes, args.error_partition_scheme)
      output_file.write(format_kill_matrix_row(killed_mutants, n_mutants, original_outcome.category==PASS))
      output_file.write('\n')