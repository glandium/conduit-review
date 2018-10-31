import errno
import exceptions
import imp
import json
import mock
import os
import sys
import unittest

review = imp.load_source(
    "review", os.path.join(os.path.dirname(__file__), os.path.pardir, "moz-phab")
)


class Helpers(unittest.TestCase):
    @mock.patch("__builtin__.open")
    @mock.patch("review.json")
    def test_read_json_field(self, m_json, m_open):
        m_open.side_effect = IOError(errno.ENOENT, "Not a file")
        self.assertEqual(None, review.read_json_field(["nofile"], ["not existing"]))

        m_open.side_effect = IOError(errno.ENOTDIR, "Not a directory")
        with self.assertRaises(IOError):
            review.read_json_field(["nofile"], ["not existing"])

        m_open.side_effect = ValueError()
        self.assertEqual(None, review.read_json_field(["nofile"], ["not existing"]))

        m_open.side_effect = None
        m_json.load.return_value = dict(a="value A", b=3)
        self.assertEqual(None, review.read_json_field(["filename"], ["not existing"]))
        self.assertEqual("value A", review.read_json_field(["filename"], ["a"]))

        m_json.load.side_effect = (
            dict(a="value A", b=3),
            dict(b="value B", c=dict(a="value CA")),
        )
        self.assertEqual(3, review.read_json_field(["file_a", "file_b"], ["b"]))
        m_json.load.side_effect = (
            dict(b="value B", c=dict(a="value CA")),
            dict(a="value A", b=3),
        )
        self.assertEqual("value B", review.read_json_field(["file_b", "file_a"], ["b"]))
        m_json.load.side_effect = (
            dict(a="value A", b=3),
            dict(b="value B", c=dict(a="value CA")),
        )
        self.assertEqual(
            "value CA", review.read_json_field(["file_a", "file_b"], ["c", "a"])
        )

    @mock.patch("__builtin__.termios", create=True)
    @mock.patch("__builtin__.tty", create=True)
    @mock.patch("review.sys")
    @unittest.skip(
        "Figure out the way to mock termios and tty imported within function"
    )
    def test_get_char(self, m_sys, m_tty, m_termios):
        m_sys.stdin.read.return_value = "x"
        self.assertEqual("x", review.get_char())
        m_termios.tcgetattr.assert_called_once()
        m_tty.setcbreak.assert_called_once()

    @mock.patch("review.get_char")
    @mock.patch("review.sys")
    def test_prompt(self, m_sys, m_get_char):
        char = None

        def get_char():
            return char

        m_get_char.side_effect = get_char

        # Return key
        char = chr(10)
        self.assertEqual("AAA", review.prompt("", ["AAA", "BBB"]))
        m_sys.stdout.write.assert_called_with("AAA\n")

        # ^C, Escape
        char = chr(13)
        self.assertEqual("AAA", review.prompt("", ["AAA", "BBB"]))
        m_sys.stdout.write.assert_called_with("AAA\n")

        m_sys.exit.side_effect = SystemExit()
        with self.assertRaises(SystemExit):
            char = chr(3)
            review.prompt("", ["AAA"])
        m_sys.stdout.write.assert_called_with("^C\n")

        with self.assertRaises(SystemExit):
            char = chr(27)
            review.prompt("", ["AAA"])
        m_sys.stdout.write.assert_called_with("^C\n")

        char = "b"
        self.assertEqual("BBB", review.prompt("", ["AAA", "BBB"]))
        m_sys.stdout.write.assert_called_with("BBB\n")

    @mock.patch("review.probe_repo")
    def test_repo_from_args(self, m_probe):
        # TODO test walking the path
        repo = None

        def probe_repo(path):
            return repo

        m_probe.side_effect = probe_repo

        class Args:
            def __init__(self, path=None):
                self.path = path

        with self.assertRaises(review.Error):
            review.repo_from_args(Args(path="some path"))

        repo = mock.MagicMock()
        args = Args(path="some path")
        self.assertEqual(repo, review.repo_from_args(args))
        repo.set_args.assert_called_once_with(args)

    def test_arc_message(self):
        self.assertEqual(
            "Title\n\nSummary:\nMessage\n\n\n\nTest Plan:\n\n"
            "Reviewers: reviewer\n\nSubscribers:\n\nBug #: 1",
            review.arc_message(
                dict(title="Title", body="Message", reviewers="reviewer", bug_id=1)
            ),
        )

        self.assertEqual(
            "Title\n\nSummary:\nMessage\n\nDepends on D123\n\nTest Plan:\n\n"
            "Reviewers: reviewer\n\nSubscribers:\n\nBug #: 1",
            review.arc_message(
                dict(
                    title="Title",
                    body="Message",
                    reviewers="reviewer",
                    bug_id=1,
                    depends_on="Depends on D123",
                )
            ),
        )

        self.assertEqual(
            "\n\nSummary:\n\n\n\n\nTest Plan:\n\nReviewers: \n\nSubscribers:\n\nBug #: ",
            review.arc_message(
                dict(title=None, body=None, reviewers=None, bug_id=None)
            ),
        )

    def test_strip_differential_revision_from_commit_body(self):
        self.assertEqual("", review.strip_differential_revision("\n\n"))
        self.assertEqual(
            "",
            review.strip_differential_revision(
                "\nDifferential Revision: http://phabricator.test/D123"
            ),
        )
        self.assertEqual(
            "",
            review.strip_differential_revision(
                "Differential Revision: http://phabricator.test/D123"
            ),
        )
        self.assertEqual(
            "title",
            review.strip_differential_revision(
                "title\nDifferential Revision: http://phabricator.test/D123"
            ),
        )
        self.assertEqual(
            "title",
            review.strip_differential_revision(
                "title\n\nDifferential Revision: http://phabricator.test/D123"
            ),
        )
        self.assertEqual(
            "title\n\nsummary",
            review.strip_differential_revision(
                "title\n\nsummary\n\nDifferential Revision: http://phabricator.test/D123"
            ),
        )

    def test_amend_commit_message_body_with_new_revision_url(self):
        self.assertEqual(
            "\nDifferential Revision: http://phabricator.test/D123",
            review.amend_revision_url("", "http://phabricator.test/D123"),
        )
        self.assertEqual(
            "title\n\nDifferential Revision: http://phabricator.test/D123",
            review.amend_revision_url("title", "http://phabricator.test/D123"),
        )
        self.assertEqual(
            "\nDifferential Revision: http://phabricator.test/D123",
            review.amend_revision_url(
                "\nDifferential Revision: http://phabricator.test/D999",
                "http://phabricator.test/D123",
            ),
        )

    @mock.patch("review.os.access")
    @mock.patch("review.os.path")
    @mock.patch("review.os.environ")
    def test_which(self, m_os_environ, m_os_path, m_os_access):
        m_os_environ.get.return_value = "/one:/two"
        m_os_path.expanduser = lambda x: x
        m_os_path.normcase = lambda x: x
        m_os_path.join = lambda x, y: "%s/%s" % (x, y)
        m_os_path.exists.side_effect = (False, True)
        m_os_access.return_value = True
        m_os_path.isdir.return_value = False

        path = "x"
        self.assertEqual("/two/x", review.which(path))

    @mock.patch("review.os.access")
    @mock.patch("review.os.path")
    @mock.patch("review.os.environ")
    @mock.patch("review.which")
    def test_which(self, m_which, m_os_environ, m_os_path, m_os_access):
        m_os_path.exists.side_effect = (True, False)
        m_os_access.return_value = True
        m_os_path.isdir.return_value = False

        path = "x"
        self.assertEqual(path, review.which_path(path))
        m_which.assert_not_called()
        review.which_path(path)
        m_which.assert_called_once_with(path)
