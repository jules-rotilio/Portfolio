import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import update_dns_cloudflare as dns  # noqa: E402


CLOUDFLARE_TRACE = (
    "fl=123abc\n"
    "h=1.1.1.1\n"
    "ip=203.0.113.42\n"
    "ts=1759670000.000\n"
    "visit_scheme=https\n"
)


def make_record(content: str, record_type: str = "A", name: str = "example.com"):
    return SimpleNamespace(
        id="record-id", name=name, type=record_type, content=content, ttl=1
    )


def make_client(records=()):
    client = mock.MagicMock()
    client.dns.records.list.return_value = list(records)
    return client


class ParseIPTests(unittest.TestCase):
    def test_parses_cloudflare_trace(self):
        self.assertEqual(dns.parse_ip(CLOUDFLARE_TRACE, 4), "203.0.113.42")

    def test_parses_plain_body_with_whitespace(self):
        self.assertEqual(dns.parse_ip("  203.0.113.42\n", 4), "203.0.113.42")

    def test_parses_ipv6(self):
        self.assertEqual(dns.parse_ip("ip=2001:db8::1\n", 6), "2001:db8::1")

    def test_rejects_wrong_family(self):
        with self.assertRaises(ValueError):
            dns.parse_ip("2001:db8::1", 4)
        with self.assertRaises(ValueError):
            dns.parse_ip("203.0.113.42", 6)

    def test_rejects_garbage(self):
        for body in ("", "<html>error</html>", "ip=not-an-ip"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                dns.parse_ip(body, 4)


class GetPublicIPTests(unittest.TestCase):
    def test_cloudflare_is_primary_source(self):
        for family in (4, 6):
            with self.subTest(family=family):
                self.assertIn("/cdn-cgi/trace", dns.IP_SOURCES[family][0])

    def test_fallbacks_are_ipify_then_ifconfig(self):
        self.assertIn("ipify.org", dns.IP_SOURCES[4][1])
        self.assertIn("ifconfig.me", dns.IP_SOURCES[4][2])

    def test_uses_primary_when_it_works(self):
        fetch = mock.Mock(return_value=CLOUDFLARE_TRACE)
        self.assertEqual(dns.get_public_ip(4, fetch), "203.0.113.42")
        fetch.assert_called_once_with(dns.IP_SOURCES[4][0], 4)

    def test_falls_back_on_http_error(self):
        fetch = mock.Mock(
            side_effect=[httpx.ConnectError("down"), "203.0.113.42"]
        )
        self.assertEqual(dns.get_public_ip(4, fetch), "203.0.113.42")
        self.assertEqual(
            [c.args[0] for c in fetch.call_args_list], dns.IP_SOURCES[4][:2]
        )

    def test_falls_back_on_invalid_body(self):
        fetch = mock.Mock(side_effect=["<html>blocked</html>", "", "203.0.113.42"])
        self.assertEqual(dns.get_public_ip(4, fetch), "203.0.113.42")
        self.assertEqual(fetch.call_count, 3)

    def test_raises_when_every_source_fails(self):
        fetch = mock.Mock(side_effect=httpx.ConnectError("down"))
        with self.assertRaises(dns.IPDetectionError) as ctx:
            dns.get_public_ip(4, fetch)
        for url in dns.IP_SOURCES[4]:
            self.assertIn(url, str(ctx.exception))


class FindDNSRecordTests(unittest.TestCase):
    def test_returns_none_when_missing(self):
        client = make_client()
        self.assertIsNone(dns.find_dns_record(client, "zone", "example.com", "A"))

    def test_queries_by_exact_name_and_type(self):
        client = make_client([make_record("1.2.3.4")])
        dns.find_dns_record(client, "zone", "example.com", "A")
        kwargs = client.dns.records.list.call_args.kwargs
        self.assertEqual(kwargs["zone_id"], "zone")
        self.assertEqual(kwargs["name"], {"exact": "example.com"})
        self.assertEqual(kwargs["type"], "A")

    def test_returns_matching_record(self):
        record = make_record("1.2.3.4")
        client = make_client([record])
        self.assertIs(dns.find_dns_record(client, "zone", "example.com", "A"), record)

    def test_rejects_record_of_other_type(self):
        client = make_client([make_record("target.example.com", record_type="CNAME")])
        with self.assertRaisesRegex(RuntimeError, "CNAME"):
            dns.find_dns_record(client, "zone", "example.com", "A")

    def test_rejects_multiple_records(self):
        client = make_client([make_record("1.2.3.4"), make_record("5.6.7.8")])
        with self.assertRaisesRegex(RuntimeError, "Found 2"):
            dns.find_dns_record(client, "zone", "example.com", "A")


class SyncDNSIPTests(unittest.TestCase):
    def sync(self, client, address="203.0.113.42"):
        out = io.StringIO()
        with redirect_stdout(out):
            dns.sync_dns_ip(client, "zone", "example.com", "A", address)
        return out.getvalue()

    def test_does_nothing_and_logs_nothing_when_up_to_date(self):
        client = make_client([make_record("203.0.113.42")])
        self.assertEqual(self.sync(client), "")
        client.dns.records.edit.assert_not_called()
        client.dns.records.create.assert_not_called()

    def test_edits_record_when_ip_changed(self):
        client = make_client([make_record("1.2.3.4")])
        output = self.sync(client)
        client.dns.records.edit.assert_called_once_with(
            dns_record_id="record-id",
            zone_id="zone",
            name="example.com",
            ttl=1,
            type="A",
            content="203.0.113.42",
        )
        self.assertIn("[UPDATE]", output)
        self.assertIn("1.2.3.4 -> 203.0.113.42", output)

    def test_never_uses_full_overwrite(self):
        # update() is a PUT that would reset proxied/comment/tags.
        client = make_client([make_record("1.2.3.4")])
        self.sync(client)
        client.dns.records.update.assert_not_called()

    def test_creates_missing_record(self):
        client = make_client()
        output = self.sync(client)
        client.dns.records.create.assert_called_once_with(
            zone_id="zone",
            name="example.com",
            ttl=1,
            type="A",
            content="203.0.113.42",
        )
        self.assertIn("Created A record", output)

    def test_does_not_touch_record_of_wrong_type(self):
        client = make_client([make_record("target.example.com", record_type="CNAME")])
        with self.assertRaises(RuntimeError):
            self.sync(client)
        client.dns.records.edit.assert_not_called()
        client.dns.records.create.assert_not_called()


@mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"})
@mock.patch.object(dns, "load_dotenv", lambda: None)
class MainTests(unittest.TestCase):
    def run_main(self, ipv6: bool, ips=None, sync_side_effect=None):
        ips = ips or {4: "203.0.113.42", 6: "2001:db8::1"}
        out = io.StringIO()
        with (
            mock.patch.object(dns, "ENABLE_IPV6", ipv6),
            mock.patch.object(dns, "Cloudflare") as cloudflare,
            mock.patch.object(dns, "get_public_ip", side_effect=lambda f: ips[f]) as get_ip,
            mock.patch.object(dns, "sync_dns_ip", side_effect=sync_side_effect) as sync,
            redirect_stdout(out),
        ):
            code = dns.main()
        return code, out.getvalue(), cloudflare, get_ip, sync

    def test_ipv6_disabled_only_syncs_a_records(self):
        code, output, cloudflare, get_ip, sync = self.run_main(ipv6=False)
        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        get_ip.assert_called_once_with(4)
        client = cloudflare.return_value
        self.assertEqual(
            [c.args for c in sync.call_args_list],
            [
                (client, zone_id, name, "A", "203.0.113.42")
                for name, zone_id in dns.DOMAINS.items()
            ],
        )

    def test_ipv6_enabled_also_syncs_aaaa_records(self):
        code, _, _, get_ip, sync = self.run_main(ipv6=True)
        self.assertEqual(code, 0)
        self.assertEqual([c.args for c in get_ip.call_args_list], [(4,), (6,)])
        record_types = [c.args[3] for c in sync.call_args_list]
        self.assertEqual(record_types, ["A"] * len(dns.DOMAINS) + ["AAAA"] * len(dns.DOMAINS))

    def test_one_failing_domain_does_not_block_the_others(self):
        code, output, _, _, sync = self.run_main(
            ipv6=False, sync_side_effect=[RuntimeError("API down"), None]
        )
        self.assertEqual(code, 1)
        self.assertEqual(sync.call_count, len(dns.DOMAINS))
        self.assertIn("[ERROR]", output)
        self.assertIn("API down", output)

    def test_ip_detection_failure_is_logged(self):
        def fail(family):
            raise dns.IPDetectionError("no network")

        out = io.StringIO()
        with (
            mock.patch.object(dns, "Cloudflare"),
            mock.patch.object(dns, "get_public_ip", side_effect=fail),
            mock.patch.object(dns, "sync_dns_ip") as sync,
            redirect_stdout(out),
        ):
            code = dns.main()
        self.assertEqual(code, 1)
        sync.assert_not_called()
        self.assertIn("[ERROR]", out.getvalue())
        self.assertIn("no network", out.getvalue())

    def test_missing_token_is_logged(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            code = dns.main()
        self.assertEqual(code, 1)
        self.assertIn("No Cloudflare API token", out.getvalue())


class DomainConfigTests(unittest.TestCase):
    def test_ipv6_disabled_by_default(self):
        self.assertFalse(dns.ENABLE_IPV6)

    def test_domains(self):
        self.assertEqual(set(dns.DOMAINS), {"example.com", "example.org"})


if __name__ == "__main__":
    unittest.main()
