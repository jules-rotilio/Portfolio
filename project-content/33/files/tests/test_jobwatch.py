import base64
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from jobwatch import __main__ as app
from jobwatch.filters import JobFilter
from jobwatch.models import Job
from jobwatch.notify import DiscordNotifier, build_embed
from jobwatch.sources.email_alerts import EmailAlertsSource, expired_alert, extract_jobs
from jobwatch.store import Store

CFG_FILTERS = {"categories": ["csharp", "python", "devops"]}


def job(title, desc="", source="francetravail", sid="1", company="", alert=False):
    return Job(source=source, source_id=sid, title=title, url="https://x", company=company,
               description=desc, from_alert=alert)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.f = JobFilter(CFG_FILTERS)

    def test_titles_matched(self):
        cases = {
            "Développeur C# .NET H/F": ["csharp"],
            "Analyste Développeur C#/SQL F/H": ["csharp"],
            "Développeur ASP.NET Core": ["csharp"],
            "Développeur Python / Django": ["python"],
            "Ingénieur DevOps - Cloud H/F": ["devops"],
            "Ingénieur Système DevOps - Cloud H/F": ["devops"],
            "SRE Kubernetes": ["devops"],
            "Développeur Fullstack Python et C#": ["csharp", "python"],
        }
        for title, cats in cases.items():
            j = job(title)
            self.assertTrue(self.f.match(j), title)
            self.assertEqual(sorted(j.categories), sorted(cats), title)

    def test_generic_title_uses_description(self):
        j = job("Analyste développeur F/H", desc="Environnement : C#, .NET, SQL Server, API REST")
        self.assertTrue(self.f.match(j))
        self.assertEqual(j.categories, ["csharp"])

    def test_rejections(self):
        for title in ["Développeur Java Spring", "Développeur C# Senior", "Lead Dev Python",
                      "Stage développeur Python", "Alternance DevOps", "Comptable", "Chef de projet"]:
            self.assertFalse(self.f.match(job(title)), title)

    def test_generic_title_without_tech_rejected(self):
        self.assertFalse(self.f.match(job("Développeur web", desc="PHP Symfony")))

    def test_alert_trusted_but_exclusions_apply(self):
        self.assertTrue(self.f.match(job("Ingénieur logiciel", alert=True)))
        self.assertFalse(self.f.match(job("Senior Software Engineer", alert=True)))


LINKEDIN_HTML = """
<table><tr><td>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&amp;refId=x"><img alt="Logo"></a>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc">Développeur C# .NET (H/F)</a>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=def">Euro-Information · Lyon (Hybride)</a>
<a href="https://www.linkedin.com/comm/jobs/view/4098765432/">Ingénieur DevOps</a>
<a href="https://www.linkedin.com/comm/jobs/view/4098765432/">Voir l'offre</a>
<a href="https://www.linkedin.com/comm/jobs/search?keywords=c%23">Voir toutes les offres</a>
<a href="https://www.linkedin.com/comm/feed">Accueil</a>
</td></tr></table>
"""

# Format 2026 : liens imbriqués, « Entreprise · Lieu » juste après le lien de l'intitulé.
LINKEDIN_2026_HTML = """
<a href="https://www.linkedin.com/comm/jobs/view/4481335795/?trk=logo"><img alt="externatic"></a>
<a href="https://www.linkedin.com/comm/jobs/view/4481335795/?trk=card"><a href="https://www.linkedin.com/comm/jobs/view/4481335795/?trk=title">Ingénieur solutions IA en Java / Python H/F</a>
<p>externatic · Lyon (Hybride)</p><p>Entre 50 k € et 55 k € par an</p><p>Recrutement actif</p></a>
<a href="https://www.linkedin.com/comm/jobs/search">Voir toutes les offres d’emploi</a>
"""

INDEED_HTML = """
<a href="https://cts.indeed.com/v3/H4sI?url=https%3A%2F%2Ffr.indeed.com%2Frc%2Fclk%2Fdl%3Fjk%3D0123456789abcdef%26from%3Dja">Développeur Python H/F</a>
<table><tr><td>AXOPEN</td></tr><tr><td>Lyon (69)</td></tr><tr><td>De 28 000 € à 33 000 € par an</td></tr></table>
<a href="https://fr.indeed.com/rc/clk/dl?jk=fedcba9876543210&amp;from=ja">Analyste développeur .NET</a>
<a href="https://fr.indeed.com/jobs?q=python">Voir plus d'offres</a>
"""

HELLOWORK_HTML = """
<a href="https://www.hellowork.com/fr-fr/emplois/63123456.html?utm_source=alerte">Développeur C# F/H</a>
<span>Recrulab</span> <span>Super recruteur</span>
<a href="#">Vénissieux - 69</a> <a href="#">CDI</a> <a href="#">43 000 - 50 000 € / an</a>
<a href="https://www.hellowork.com/fr-fr/emplois/63123456.html">Voir l’offre</a>
<a href="https://track.hellowork.com/click?u=https%3A%2F%2Fwww.hellowork.com%2Ffr-fr%2Femplois%2F63999999.html">Ingénieur DevOps</a>
"""

# Comme les vrais e-mails : intitulé, <br>, puis « entreprise - » et « département - ville » dans le même lien.
FRANCETRAVAIL_HTML = """
<p><span> 2 nouvelles offres publi&eacute;es pour votre alerte "Csharp". </span></p>
<table><tr>
<td><img alt="" src="https://cdn.francetravail.fr/logo.png"></td>
<td><a href="https://candidat.francetravail.fr/offres/recherche/detail/7682488?at_medium=CMP&amp;at_campaign=DSI"><span>Développeur c# junior F/H <br><!-- Lieu offre -->
<span>IRIUM SOFTWARE - </span> <span>26 - Bourg-de-Péage</span></span></a></td>
</tr><tr><td colspan="2"><span>CDI</span></td></tr>
<tr><td colspan="2"><p>Offre n°7682488</p></td></tr></table>
<table><tr><td><a href="https://candidat.francetravail.fr/offres/recherche/detail/201XKQB?at_medium=CMP"><span>Ingénieur DevOps (H/F) <br><span>69 - Lyon</span></span></a></td></tr></table>
<table><tr><td><a href="https://candidat.francetravail.fr/offres/recherche/detail/7066299?at_medium=CMP"><span>Développeur Python (H/F) / Freelance <br><span>Île-de-France</span></span></a></td></tr></table>
<a href="https://candidat.francetravail.fr/offres/recherche?at_medium=CMP">Voir plus d'offres</a>
"""

FRANCETRAVAIL_EXPIRED_HTML = """
<p>Nous vous informons que votre alerte emploi &quot;Csharp&quot; est arriv&eacute;e &agrave; &eacute;ch&eacute;ance
et a &eacute;t&eacute; supprim&eacute;e.</p>
"""


class EmailParsingTests(unittest.TestCase):
    def test_linkedin(self):
        jobs = extract_jobs(LINKEDIN_HTML, "linkedin")
        self.assertEqual([j.source_id for j in jobs], ["4012345678", "4098765432"])
        self.assertEqual(jobs[0].title, "Développeur C# .NET (H/F)")
        self.assertEqual(jobs[0].company, "Euro-Information")
        self.assertEqual(jobs[0].location, "Lyon (Hybride)")
        self.assertEqual(jobs[0].url, "https://www.linkedin.com/jobs/view/4012345678/")
        self.assertEqual(jobs[1].title, "Ingénieur DevOps")
        self.assertTrue(all(j.from_alert for j in jobs))

    def test_indeed_with_tracking_redirect(self):
        jobs = extract_jobs(INDEED_HTML, "indeed")
        self.assertEqual([j.source_id for j in jobs], ["0123456789abcdef", "fedcba9876543210"])
        self.assertEqual(jobs[0].url, "https://fr.indeed.com/viewjob?jk=0123456789abcdef")
        self.assertEqual((jobs[0].company, jobs[0].location), ("AXOPEN", "Lyon (69)"))
        self.assertEqual(jobs[1].company, "")  # rien après le lien : pas d'entreprise inventée

    def test_linkedin_company_after_link(self):
        jobs = extract_jobs(LINKEDIN_2026_HTML, "linkedin")
        self.assertEqual([j.source_id for j in jobs], ["4481335795"])
        self.assertEqual((jobs[0].title, jobs[0].company, jobs[0].location),
                         ("Ingénieur solutions IA en Java / Python H/F", "externatic", "Lyon (Hybride)"))

    def test_hellowork(self):
        jobs = extract_jobs(HELLOWORK_HTML, "hellowork")
        self.assertEqual([j.source_id for j in jobs], ["63123456", "63999999"])
        self.assertEqual((jobs[0].company, jobs[0].location, jobs[0].contract), ("Recrulab", "Vénissieux - 69", "CDI"))
        self.assertEqual(jobs[1].title, "Ingénieur DevOps")

    def test_hellowork_base64_tracking_link(self):
        target = "moi@example.fr🪢https://www.hellowork.com/fr-fr/emplois/81559168.html?utm_source=jobalert"
        token = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
        html = (f'<a href="https://emails.hellowork.com/clic/abc/3/def/{token}">Développeur C# .Net H/F</a>'
                f'<a href="https://emails.hellowork.com/clic/abc/5/ghi/{token}">Voir l’offre</a>')
        jobs = extract_jobs(html, "hellowork")
        self.assertEqual([j.source_id for j in jobs], ["81559168"])
        self.assertEqual(jobs[0].title, "Développeur C# .Net H/F")

    def test_francetravail(self):
        jobs = extract_jobs(FRANCETRAVAIL_HTML, "francetravail")
        self.assertEqual([j.source_id for j in jobs], ["7682488", "201XKQB", "7066299"])
        self.assertEqual((jobs[0].title, jobs[0].company, jobs[0].location),
                         ("Développeur c# junior F/H", "IRIUM SOFTWARE", "26 - Bourg-de-Péage"))
        self.assertEqual(jobs[0].url, "https://candidat.francetravail.fr/offres/recherche/detail/7682488")
        self.assertEqual((jobs[1].company, jobs[1].location), ("", "69 - Lyon"))  # entreprise non indiquée
        self.assertEqual((jobs[2].company, jobs[2].location), ("", "Île-de-France"))  # lieu = région

    def test_francetravail_expired_alert(self):
        self.assertEqual(expired_alert(FRANCETRAVAIL_EXPIRED_HTML, "francetravail"), "Csharp")
        self.assertIsNone(expired_alert(FRANCETRAVAIL_HTML, "francetravail"))
        self.assertIsNone(expired_alert(FRANCETRAVAIL_EXPIRED_HTML, "linkedin"))

    def test_folders_per_site(self):
        src = EmailAlertsSource({"folder": "Alertes", "folders": {
            "linkedin": "INBOX/Jobs/Linkedin", "francetravail": ["INBOX/Jobs/France Travail", "INBOX"]}}, "u", "p")
        self.assertEqual(src.folders("linkedin"), ["INBOX/Jobs/Linkedin"])
        self.assertEqual(src.folders("francetravail"), ["INBOX/Jobs/France Travail", "INBOX"])
        self.assertEqual(src.folders("indeed"), ["Alertes"])
        self.assertEqual(EmailAlertsSource({}, "u", "p").folders("indeed"), ["INBOX"])


class StoreTests(unittest.TestCase):
    def test_dedupe_by_key_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(os.path.join(d, "x.db"))
            a = job("Développeur C# H/F", company="Euro-Information", sid="A")
            self.assertTrue(s.is_empty())
            s.add(a, notified=True)
            self.assertTrue(s.is_known(a))
            same_elsewhere = job("Développeur C# (F/H)", company="EURO-INFORMATION", source="linkedin", sid="Z")
            self.assertTrue(s.is_known(same_elsewhere))
            other = job("Développeur Python", company="Euro-Information", sid="B")
            self.assertFalse(s.is_known(other))


class NotifyTests(unittest.TestCase):
    def test_embed(self):
        j = job("Dev C#", desc="x" * 1000, company="ACME")
        j.location, j.categories = "Lyon", ["csharp"]
        j.published = datetime(2026, 10, 21, tzinfo=timezone.utc)
        e = build_embed(j)
        self.assertEqual(e["footer"]["text"], "France Travail · C#/.NET")
        self.assertLessEqual(len(e["description"]), 280)
        self.assertEqual([(f["name"], f["value"]) for f in e["fields"]], [("Entreprise", "ACME"), ("Lieu", "Lyon")])

    def test_embed_without_details(self):
        e = build_embed(job("Dev C#"))
        self.assertNotIn("fields", e)
        self.assertNotIn("description", e)

    def test_one_message_per_job(self):
        n = DiscordNotifier("https://discord.invalid/hook", mention="<@42>")
        with mock.patch("jobwatch.notify.request") as req, mock.patch("jobwatch.notify.time.sleep"):
            n.send_jobs([job(f"Dev C# {i}", sid=str(i), company="ACME") for i in range(3)])
        self.assertEqual(req.call_count, 3)
        payloads = [c.kwargs["json_body"] for c in req.call_args_list]
        self.assertTrue(all(len(p["embeds"]) == 1 for p in payloads))
        self.assertEqual(payloads[0]["content"], "<@42> Dev C# 0 · ACME")

    def test_send_test(self):
        n = DiscordNotifier("https://discord.invalid/hook", mention="<@42>")
        with mock.patch("jobwatch.notify.request") as req:
            n.send_test()
        payload = req.call_args.kwargs["json_body"]
        self.assertTrue(payload["content"].startswith("<@42> "))
        self.assertIn("users", payload["allowed_mentions"]["parse"])
        self.assertIn("EXEMPLE", payload["embeds"][0]["title"])


class RunOnceTests(unittest.TestCase):
    def test_end_to_end(self):
        class FakeSource:
            name = "fake"
            def __init__(self, jobs): self.jobs = jobs
            def fetch(self): return list(self.jobs)

        class Broken:
            name = "broken"
            def fetch(self): raise RuntimeError("panne")

        jobs = [job("Développeur C#", sid="1"), job("Développeur Java", sid="2"),
                job("Ingénieur DevOps", sid="3")]
        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "x.db"))
            notifier = mock.Mock()
            cfg = {"general": {"first_run_limit": 15}}
            n = app.run_once(cfg, [FakeSource(jobs), Broken()], store, JobFilter(CFG_FILTERS), notifier)
            self.assertEqual(n, 2)
            sent = notifier.send_jobs.call_args.args[0]
            self.assertEqual({j.title for j in sent}, {"Développeur C#", "Ingénieur DevOps"})
            notifier.send_text.assert_called_once()  # alerte sur la source en panne
            # 2e passage : rien de nouveau
            notifier.reset_mock()
            self.assertEqual(app.run_once(cfg, [FakeSource(jobs)], store, JobFilter(CFG_FILTERS), notifier), 0)
            notifier.send_jobs.assert_not_called()

    def test_notice_sent_once(self):
        class AlertSource:
            name = "email"
            notices = [("francetravail:<1@ft>", "⏰ alerte expirée"), ("francetravail:<1@ft>", "⏰ alerte expirée")]
            def fetch(self): return []

        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "x.db"))
            notifier = mock.Mock()
            for _ in range(2):  # le même e-mail est revu au passage suivant
                app.run_once({}, [AlertSource()], store, JobFilter(CFG_FILTERS), notifier)
            notifier.send_text.assert_called_once_with("⏰ alerte expirée")


if __name__ == "__main__":
    unittest.main()
