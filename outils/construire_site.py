#!/usr/bin/env python3
"""Construit index.html à partir de donnees/paroisse.json et modele/page.html.

Usage : python3 outils/construire_site.py [--date AAAA-MM-JJ] [--purger]

--purger  retire de la base les éléments périmés (messes passées, annonces
          échues, carnet plus ancien que duree_carnet_jours) avant construction.
--date    date de référence (par défaut : aujourd'hui, heure de Paris).
"""
import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees" / "paroisse.json"
MODELE = RACINE / "modele" / "page.html"
SORTIE = RACINE / "index.html"

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def e(txt):
    return html.escape(str(txt), quote=True)


def d(s):
    return dt.date.fromisoformat(s)


def date_longue(s, jour_semaine=True, annee=False):
    x = d(s)
    j = "1er" if x.day == 1 else str(x.day)
    txt = f"{j} {MOIS[x.month - 1]}"
    if annee:
        txt += f" {x.year}"
    if jour_semaine:
        txt = f"{JOURS[x.weekday()].capitalize()} {txt}"
    return txt


def heure(h):
    hh, mm = h.split(":")
    return f"{int(hh)} h {mm}"


def purger(base, auj):
    p = base["parametres"]
    base["messes"] = [m for m in base["messes"] if d(m["date"]) >= auj]
    base["jours"] = [j for j in base["jours"] if d(j["date"]) >= auj]
    base["annonces"] = [a for a in base["annonces"]
                        if not a.get("date_fin") or d(a["date_fin"]) >= auj]
    limite = auj - dt.timedelta(days=p.get("duree_carnet_jours", 45))
    for k in base["carnet"]:
        base["carnet"][k] = [c for c in base["carnet"][k] if d(c["date"]) >= limite]


def section_messes(base, auj):
    p = base["parametres"]
    libelles = {j["date"]: j["libelle"] for j in base["jours"]}
    messes = sorted((m for m in base["messes"] if d(m["date"]) >= auj),
                    key=lambda m: (m["date"], m["heure"]))
    blocs = []
    dates = []
    for m in messes:
        if m["date"] not in dates:
            dates.append(m["date"])
    for jour in dates:
        lignes = []
        for m in (x for x in messes if x["date"] == jour):
            lieu = m["lieu"]
            edifice = m.get("edifice") or base["lieux"].get(lieu, "")
            txt = f'<span class="h">{e(heure(m["heure"]))}</span> · <span class="lieu">{e(lieu)}</span>'
            if edifice and not lieu.endswith(")"):
                txt += f", {e(edifice)}"
            details = []
            if m.get("nature"):
                details.append(e(m["nature"]))
            if p.get("afficher_intentions") and m.get("intentions"):
                details.append(" ; ".join(e(i) for i in m["intentions"]))
            if details:
                txt += f'<span class="intentions">{"<br>".join(details)}</span>'
            lignes.append(f'<p class="cel">{txt}</p>')
        lib = libelles.get(jour, "")
        petit = f"<small>{e(lib)}</small>" if lib else ""
        blocs.append(f'<div class="jour"><div class="date">{e(date_longue(jour))}{petit}</div>'
                     f'<div>{"".join(lignes)}</div></div>')
    if not blocs:
        blocs.append('<p class="lede">Les prochains horaires seront publiés à réception de la feuille paroissiale.</p>')
    maj = base["mise_a_jour"]
    note = (f'<div class="note-maj">Dernière mise à jour : {e(maj["source"])}. '
            "La feuille complète est disponible à l'accueil du presbytère et au fond des églises.</div>")
    return ('<section id="messes"><div class="wrap"><h2>Messes et célébrations</h2>'
            '<p class="lede">Horaires des prochains jours, dans les églises de la paroisse.</p>'
            + "".join(blocs) + note + "</div></section>")


def cartes(items):
    return "".join(f'<li><h3>{e(a["titre"])}</h3><p>{e(a["texte"])}</p></li>' for a in items)


def section_annonces(base, auj):
    items = [a for a in base["annonces"] if not a.get("date_fin") or d(a["date_fin"]) >= auj]
    corps = (f'<ul class="annonces">{cartes(items)}</ul>' if items
             else '<p class="lede">Aucune annonce en cours.</p>')
    return ('<section id="annonces"><div class="wrap"><h2>Annonces</h2>'
            '<p class="lede">La vie de la paroisse en ce moment.</p>' + corps + "</div></section>")


def section_carnet(base):
    if not base["parametres"].get("afficher_carnet"):
        return ""
    titres = [("baptemes", "Baptêmes"), ("mariages", "Mariages"), ("obseques", "Obsèques")]
    cols = []
    for cle, titre in titres:
        lst = sorted(base["carnet"].get(cle, []), key=lambda c: c["date"])
        if not lst:
            continue
        lis = "".join(f'<li>{e(c["noms"])}<small>le {e(date_longue(c["date"], False))} à {e(c["lieu"])}</small></li>'
                      for c in lst)
        cols.append(f"<div><h3>{titre}</h3><ul>{lis}</ul></div>")
    if not cols:
        return ""
    return ('<section id="carnet"><div class="wrap"><h2>Carnet paroissial</h2>'
            '<p class="lede">Baptêmes, mariages et obsèques célébrés dans la paroisse.</p>'
            f'<div class="carnet">{"".join(cols)}</div></div></section>')


def section_paroisse(base):
    pr = base["presentation"]
    lis = "".join(f'<li><b>{e(c)}</b><span>{e(base["lieux"].get(c, "").capitalize())}</span></li>'
                  for c in pr["clochers"])
    return ('<section id="paroisse"><div class="wrap"><h2>La paroisse</h2>'
            f'<p class="lede">{e(pr["texte"])}</p><ul class="clochers">{lis}</ul></div></section>')


def section_vie(base):
    return ('<section id="vie"><div class="wrap"><h2>Vie paroissiale</h2>'
            f'<ul class="annonces">{cartes(base["vie_paroissiale"])}</ul></div></section>')


def section_contact(base):
    c = base["contact"]
    adr = e(c["adresse"]).replace(", ", "<br>", 1)
    return ('<section id="contact"><div class="wrap"><h2>Contact et accueil</h2><div class="contact">'
            f'<div><h3>Accueil au presbytère</h3><p>{e(c["accueil"])}</p></div>'
            f'<div><h3>Adresse</h3><p class="val">{adr}</p></div>'
            f'<div><h3>Téléphone et courriel</h3><p><span class="val">{e(c["telephone"])}</span><br>'
            f'<span class="val">{e(c["courriel"])}</span></p></div>'
            "</div></div></section>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--purger", action="store_true")
    a = ap.parse_args()
    auj = d(a.date) if a.date else dt.datetime.now(ZoneInfo("Europe/Paris")).date()

    base = json.loads(DONNEES.read_text(encoding="utf-8"))
    if a.purger:
        purger(base, auj)
        DONNEES.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    carnet = section_carnet(base)
    sections = "\n".join(filter(None, [
        section_messes(base, auj), section_annonces(base, auj), carnet,
        section_paroisse(base), section_vie(base), section_contact(base)]))
    page = MODELE.read_text(encoding="utf-8")
    bandeau = base["parametres"].get("bandeau")
    page = page.replace("{{BANDEAU}}", f'<div class="demo">{e(bandeau)}</div>' if bandeau else "")
    page = (page.replace("{{ACCROCHE}}", e(base["presentation"]["accroche"]))
                .replace("{{NAV_CARNET}}", '<a href="#carnet">Carnet</a>' if carnet else "")
                .replace("{{SECTIONS}}", sections)
                .replace("{{DATE_MAJ}}", e(date_longue(base["mise_a_jour"]["date"], False, True))))
    SORTIE.write_text(page, encoding="utf-8")
    print(f"index.html construit ({len(page)} caractères), référence {auj}")


if __name__ == "__main__":
    sys.exit(main())
