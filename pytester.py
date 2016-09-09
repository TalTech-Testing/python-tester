import json
import logging
import os
import subprocess
import sys

from shutil import copy2, Error, copystat

import re

from hodorcommon.common import get_logger, get_source_list
import xml.etree.ElementTree as ET

def sh(cmd):
    """
    Executes the command.
    Returns (returncode, stdout, stderr, Popen object)
    """
    # print cmd
    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=True)
    out, err = p.communicate()
    # print 'exit code', p.returncode
    return p.returncode, out.decode('utf-8'), err.decode('utf-8'), p


def copyfiles(src, dst, ignore=None):
    """
    https://docs.python.org/2/library/shutil.html#copytree-example
    with some modifications (destination folder can exist)
    """
    names = sorted(os.listdir(src))
    files = []
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    if not os.path.exists(dst):
        os.makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if os.path.isdir(srcname):
                files += copyfiles(srcname, dstname, ignore)
            else:
                copy2(srcname, dstname)
                files += [dstname]
                # XXX What about devices, sockets etc.?
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error as err:
            errors.extend(err.args[0])
    try:
        copystat(src, dst)
    except WindowsError:
        # can't copy file access times on Windows
        pass
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise Error(errors)
    return files


def validate_flake8(filename):
    logger = get_logger()
    cmd = "flake8 --statistics --ignore=E501 --max-complexity 10 " + filename
    (exitval, out, err, p) = sh(cmd)
    flake8_violation = False
    if len(err) > 0 or len(out) > 0:
        logger.debug("FLAKE8 error output: " + str(err))
        m_feedback = re.search(r'^(.*)/.*:', out, re.MULTILINE)
        if m_feedback is not None:
            out = out.replace(m_feedback.group(1) + "/", "")
        flake8_violation = True
    return (out, flake8_violation)


def validate_pep257(filename):
    logger = get_logger()
    cmd = "pep257 " + filename
    (exitval, out, err, p) = sh(cmd)
    pep257_violation = False
    if len(err) > 0 or len(out) > 0:
        logger.debug("PEP257 error output: " + str(err))
        m_feedback = re.search(r'^(.*)/.*:', err, re.MULTILINE)
        if m_feedback is not None:
            err = err.replace(m_feedback.group(1) + "/", "")
        pep257_violation = True
    return (err, pep257_violation)

def test(json_string):
    data = json.loads(json_string)
    """
    data has:
    "contentRoot" - points to the folder where content (source) is stored
    "testRoot" - folder where the test files are stored
    "extra" - additional information

    All the files in contentRoot and testRoot should remain unchanged
    (that way it is possible to re-run the tester)
    """
    session = None
    if 'session' in data:
        session = data['session']
    logger = get_logger(session)
    logger.debug('start now pytest')
    # debug for localhost
    logger.logger.addHandler(logging.StreamHandler())
    try:
        sourcefrom = data['contentRoot']
        testfrom = data['testRoot']
        # read possible extra field
        extra = ''
        if 'extra' in data:
            extra = data['extra']

        # one dir up from content root, should end up in "/host"
        testroot = os.path.dirname(data['contentRoot'].rstrip('/'))
        testpath = os.path.join(testroot, 'pytest_tmp')

        # copy both contents and tests to testpath
        sourcefiles = copyfiles(sourcefrom, testpath)
        testfiles = copyfiles(testfrom, testpath)

        pytest_output_file = os.path.join(testroot, 'pytest_output.json')
        pytest_output_xml = os.path.join(testroot, 'pytext_output.xml')
        resultfile = os.path.join(testroot, 'output.json')

        # DEBUG bljät
        cmd = "tree /host"
        _, out, _, _ = sh(cmd)
        logger.debug('TREE /host BEFORE:\n' + str(out))

        cmd = "tree"
        _, out, _, _ = sh(cmd)
        logger.debug('TREE . BEFORE:\n' + str(out))


        timeout = 60
        # sent to worker
        results_list = []
        results_output = ""

        grade_number = 1
        results_total_count = 0
        results_total_passed = 0

        exitval = 0

        # source
        source_list = []
        try:
            logger.debug('reading source from:' + sourcefrom)
            source_list = get_source_list(sourcefrom, allowed_extensions=['py'])
        except:
            logger.exception("Error while getting source list")

        is_error = False # it True, skip the rest

        # let's check whether source compiles
        for sourcefile in sourcefiles:
            if sourcefile[-3:] != '.py': continue # only py files
            cmd = "python3 -m py_compile " + sourcefile
            (exitval, out, err, _) = sh(cmd)
            if len(err) > 0:
                m_filename = re.finditer(r'File.*"(.*)"', err, re.MULTILINE)
                if m_filename is not None:
                    for fail in m_filename:
                        err = err.replace(fail.group(1), "!?!?!?!")
                stroutput = "Syntax error detected\n\n" + err
                result = {'output': stroutput,
                          'extra': "",
                          'results': [{'percent': 0.0, 'name': 'grade1',
                                       'code': 1,
                                       'output': stroutput}],
                          # [{'percent': 100.0, 'title': 'style', 'output': 'Code conforms to style guidelines'} ... }
                          'percent': 0,
                          'source': source_list
                          }
                is_error = True
                with open(resultfile, 'w') as f:
                    json.dump(result, f)
                break

        if not is_error:
            # checkstyle
            if 'stylecheck' in extra or 'checkstyle' in extra:
                results_output += "Style conventions checker results:\n"
                flake8_violation = False
                pep257_violation = False
                flake8_disabled = False
                logger.info("Checking style!")
                for sourcefile in sourcefiles:
                    logger.debug("Checking style for " + sourcefile)
                    if sourcefile[-3:] != '.py':
                        logger.debug('Not a py-file')
                        continue
                    logger.debug("Checking flake8!")
                    (flake8_feedback, violation) = validate_flake8(sourcefile)
                    results_output += flake8_feedback
                    if violation:
                        flake8_violation = True
                    logger.debug("Checking pep257!")
                    (pep257_feedback, violation) = validate_pep257(sourcefile)
                    results_output += pep257_feedback
                    if violation:
                        pep257_violation = True
                    # Check whether the code has codechecker disable commands
                    try:
                        with open(sourcefile) as content_file:
                            content = content_file.read()
                            if "# flake8: noqa" in content or "# noqa" in content:
                                flake8_disabled = True
                                logger.warning("noqa tag found in file!")
                    except:
                        logger.error("Unable to open file for reading!")
                        results_output = "Unable to open file for reading"
                    if flake8_disabled:
                        results_output += "\n\nStyle checker disabling directives found in source code! Please remove (noqa) and try again!\n\n"
                    else:
                        if not flake8_violation:
                            results_output += "Code conforms to PEP8 (coding style) guidelines! Good job!\n"
                        if not pep257_violation:
                            results_output += "Code conforms to PEP257 (docstring conventions) guidelines! Great work!\n"
                        results_output += "\n"
                # Add results to final results
                logger.debug("Adding style results to array!")
                if not flake8_violation and not pep257_violation and not flake8_disabled:
                    results_list.append(
                        {'percent': 100.0, 'name': 'Stylecheck_1', 'code': 101,
                         'output': 'Code conforms to style guidelines'})
                else:
                    results_list.append(
                        {'percent': 0.0, 'name': 'Stylecheck_1', 'code': 101,
                         'output': 'Code does not conform to style guidelines'})

            pass

        if not is_error:
            for testfile in testfiles:
                if testfile[-3:] != '.py': continue # only py files


                results_count = 0
                results_passed = 0
                results_failed = 0
                cmd = "timeout {} pytest --json={} --junitxml={} {}".format(timeout, pytest_output_file, pytest_output_xml, testfile)

                (exitval, out, err, _) = sh(cmd)
                logger.debug("Executed: " + cmd)
                logger.debug("sterr: " + err)
                logger.debug("stdout: " + out)
                logger.debug('return code:' + str(exitval))
                # results_output = ""
                testname = os.path.basename(testfile)
                results_output += "Test: {}\n".format(testname)
                try:
                    logger.debug('reading output file:' + pytest_output_file)
                    pytest_data = json.load(open(pytest_output_file, 'r'))
                    logger.debug('contents:' + str(pytest_data))
                    if 'report' in pytest_data:
                        # "summary": {"duration": 0.036809444427490234, "num_tests": 3, "passed": 1, "failed": 2},
                        if 'summary' in pytest_data['report']:
                            summary_data = pytest_data['report']['summary']
                            if 'num_tests' in summary_data:
                                results_count = summary_data['num_tests']
                            if 'passed' in summary_data:
                                results_passed = summary_data['passed']
                            if 'failed' in summary_data:
                                results_failed = summary_data['failed']
                        if 'tests' in pytest_data['report']:
                            for testdata in pytest_data['report']['tests']:
                                tokens = testdata['name'].split('::')
                                if len(tokens) == 2:
                                    results_output += tokens[1] + ": " + testdata['outcome'] + "\n"
                                if testdata['outcome'] == 'failed' and 'call' in testdata:
                                    if testdata['call']['outcome'] == 'failed':
                                        failed_message = testdata['call']['longrepr']
                                        logger.debug('Fail message:\n' + failed_message)
                                        for line in failed_message.split('\n'):
                                            if len(line) > 0 and line[0] == 'E':
                                                results_output += "  " + line[1:]


                    if results_count == 0:
                        results_output += "\nErrors in the code."
                    if results_count >= 0:
                        results_output += "\n\nTotal number of tests: {}\n".format(results_count)
                        results_output += "Passed tests: {}\n".format(results_passed)
                        results_output += "Failed tests: {}\n".format(results_failed)
                        results_percent = 0
                        if results_count > 0:
                            results_percent = results_passed / results_count
                        results_output += "\nPercentage: {:.2%}\n\n".format(results_percent)
                        results_list.append({'percent': results_percent * 100, 'name': 'Grade_' + str(grade_number),
                                             'code': str(grade_number), 'output': 'todo?',
                                             'stdout': out, 'stderr': err})
                        results_total_count += results_count
                        results_total_passed += results_passed
                    else:
                        # possible error, let's check xml output
                        # as this mainly applies for test errors, no point to show those.
                        tree = ET.parse(pytest_output_xml)
                        root = tree.getroot()
                        error_message = root[0][0].text
                        """
                        for line in error_message:
                            if line[0] == 'E':
                                # let's check only "E" lines
                                pass
                        """
                        logger.debug('error message from XML:\n' + error_message)
                        pass
                    grade_number += 1

                except:
                    logger.exception("Error while parsing pytest output json")
                    pass


            if int(exitval) > 123:
                # timeout, let's build our own json
                d = {
                    'results': [
                        {'code': 1, 'percent': 0},
                        {'code': 101, 'percent': 0}
                    ],
                    'percent': 0,
                    'output': 'Programmi testimiseks lubatud aeg on möödas. Sinu programm töötas liiga kaua ja ei andnud vastust. Proovi oma programmi parandada.\n\nSession:' + str(session),
                    'source':[]
                }
                with open(resultfile, 'w') as f:
                    json.dump(d, f)
            else:
                # no timeout
                results_total_percent = 0
                if results_total_count > 0:
                    results_total_percent = results_total_passed / results_total_count

                d = {
                    'results': results_list,
                    'output': results_output,
                    'percent': results_total_percent,
                    'source': source_list,
                    'extra': 'todo?'
                }
                with open(resultfile, 'w') as f:
                    json.dump(d, f)

        # DEBUG bljät
        cmd = "tree /host"
        _, out, _, _ = sh(cmd)
        logger.debug('TREE /host AFTER:\n' + str(out))

        cmd = "tree"
        _, out, _, _ = sh(cmd)
        logger.debug('TREE . AFTER:\n' + str(out))

        with open(resultfile, 'r') as f:
            result_json = f.read()
            logger.debug('result:' + str(result_json))
            return str(result_json)
    except:
        logger.exception("Error while executing python tester")
    return None


if __name__ == '__main__':
    json_string = "".join(sys.stdin)
    result = test(json_string)
    print(result)