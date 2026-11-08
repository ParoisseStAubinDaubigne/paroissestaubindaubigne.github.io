#!/usr/bin/env python3
"""Construit les pages du site à partir de donnees/paroisse.json et modele/page.html.

Usage : python3 outils/construire_site.py [--date AAAA-MM-JJ] [--purger]

--purger  retire de la base les éléments périmés (messes et événements passés,
          annonces échues, carnet plus ancien que duree_carnet_jours) avant construction.
--date    date de référence (par défaut : aujourd'hui, heure de Paris).

Pages produites : index.html, messes.html, agenda.html, vie-paroissiale.html,
paroisse.html, contact.html, questions.html.
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

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_COURT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
              "août", "sept.", "oct.", "nov.", "déc."]

PAGES = [
    ("index.html", "Accueil"),
    ("messes.html", "Messes"),
    ("agenda.html", "Agenda"),
    ("questions.html", "Vos questions"),
    ("vie-paroissiale.html", "Vie paroissiale"),
    ("paroisse.html", "La paroisse"),
    ("contact.html", "Contact"),
]


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


def fin_evenement(ev):
    return d(ev.get("date_fin") or ev["date"])


# ---------------------------------------------------------------- purge

def purger(base, auj):
    p = base["parametres"]
    base["messes"] = [m for m in base["messes"] if d(m["date"]) >= auj]
    base["jours"] = [j for j in base["jours"] if d(j["date"]) >= auj]
    base["annonces"] = [a for a in base["annonces"]
                        if not a.get("date_fin") or d(a["date_fin"]) >= auj]
    base["evenements"] = [v for v in base.get("evenements", []) if fin_evenement(v) >= auj]
    limite = auj - dt.timedelta(days=p.get("duree_carnet_jours", 45))
    for k in base["carnet"]:
        base["carnet"][k] = [c for c in base["carnet"][k] if d(c["date"]) >= limite]


# ---------------------------------------------------------------- blocs

def bloc_messes(base, auj, jusqu_au=None):
    p = base["parametres"]
    libelles = {j["date"]: j["libelle"] for j in base["jours"]}
    messes = sorted((m for m in base["messes"]
                     if d(m["date"]) >= auj and (jusqu_au is None or d(m["date"]) <= jusqu_au)),
                    key=lambda m: (m["date"], m["heure"]))
    dates = []
    for m in messes:
        if m["date"] not in dates:
            dates.append(m["date"])
    blocs = []
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
        return '<p class="vide">Les prochains horaires seront publiés à réception de la feuille paroissiale.</p>'
    return "".join(blocs)


def bloc_evenements(base, auj, nombre=None):
    evs = sorted((v for v in base.get("evenements", []) if fin_evenement(v) >= auj),
                 key=lambda v: (v["date"], v.get("heure", "")))
    if nombre:
        evs = evs[:nombre]
    if not evs:
        return '<p class="vide">Aucun événement annoncé pour le moment.</p>'
    items = []
    for v in evs:
        x = d(v["date"])
        quand = date_longue(v["date"])
        if v.get("date_fin") and v["date_fin"] != v["date"]:
            quand = f"Du {date_longue(v['date'], False)} au {date_longue(v['date_fin'], False)}"
        if v.get("heure"):
            quand += f" à {heure(v['heure'])}"
        if v.get("lieu"):
            quand += f" · {v['lieu']}"
        img = f'<img src="{e(v["image"])}" alt="Affiche : {e(v["titre"])}" loading="lazy">' if v.get("image") else ""
        items.append(
            f'<li class="evt"><div class="cal"><b>{x.day}</b><span>{MOIS_COURT[x.month - 1]}</span></div>'
            f'<div><h3>{e(v["titre"])}</h3><p class="quand">{e(quand)}</p>'
            f'<p>{e(v.get("texte", ""))}</p>{img}</div></li>')
    return f'<ul class="evts">{"".join(items)}</ul>'


def cartes(items, classe="annonces"):
    if not items:
        return '<p class="vide">Aucune annonce en cours.</p>'
    lis = "".join(f'<li><h3>{e(a["titre"])}</h3><p>{e(a["texte"])}</p></li>' for a in items)
    return f'<ul class="{classe}">{lis}</ul>'


def annonces_en_cours(base, auj):
    return [a for a in base["annonces"] if not a.get("date_fin") or d(a["date_fin"]) >= auj]


def section(ident, titre, lede, corps, niveau=2):
    l = f'<p class="lede">{lede}</p>' if lede else ""
    return (f'<section id="{ident}"><div class="wrap"><h{niveau}>{titre}</h{niveau}>'
            f'{l}{corps}</div></section>')


def note_maj(base):
    maj = base["mise_a_jour"]
    return (f'<div class="note-maj">Dernière mise à jour : {e(maj["source"])}. '
            "La feuille complète est disponible à l'accueil du presbytère et au fond des églises.</div>")


def bloc_carnet(base):
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
    return section("carnet", "Carnet paroissial",
                   "Baptêmes, mariages et obsèques célébrés dans la paroisse.",
                   f'<div class="carnet">{"".join(cols)}</div>')


def bloc_appel(base, lien=True):
    a = base["accueil_foi"]
    bouton = ('<div class="boutons"><a class="bouton" href="questions.html">Questions fréquentes</a>'
              '<a class="bouton clair" href="contact.html#question">Être contacté</a></div>') if lien else ""
    return (f'<section class="bande-appel"><div class="wrap"><div class="appel">'
            f'<div><h2>{e(a["titre"])}</h2><p>{e(a["texte"])}</p></div>{bouton}</div></div></section>')


def bloc_coordonnees(base):
    c = base["contact"]
    adr = e(c["adresse"]).replace(", ", "<br>", 1)
    return ('<div class="contact">'
            f'<div><h3>Accueil au presbytère</h3><p>{e(c["accueil"])}</p></div>'
            f'<div><h3>Adresse</h3><p class="val">{adr}</p></div>'
            f'<div><h3>Téléphone et courriel</h3><p><span class="val">{e(c["telephone"])}</span><br>'
            f'<span class="val">{e(c["courriel"])}</span></p></div></div>')


def bloc_formulaire(base):
    f = base["formulaire"]
    c = base["contact"]
    actif = f.get("actif")
    if actif and f.get("type") == "lien" and f.get("lien"):
        return (f'<p><a class="bouton" href="{e(f["lien"])}" target="_blank" rel="noopener">'
                "Ouvrir le formulaire</a></p>")
    avis = "" if actif else (
        '<p class="avis">Formulaire en cours de mise en place : l\'envoi n\'est pas encore activé. '
        f'En attendant, l\'accueil du presbytère répond au {e(c["telephone"])}.</p>')
    action = f' action="{e(f["adresse_envoi"])}" method="post"' if actif and f.get("adresse_envoi") else ""
    dis = "" if actif else " disabled"
    rgpd = (f'Votre message est lu uniquement par {e(f["destinataire"])}, qui vous répond {e(f["delai_reponse"])}. '
            f'Il est conservé {e(f["conservation"])} au plus, puis supprimé ; il n\'est ni publié ni transmis à des tiers. '
            "Vous pouvez demander à tout moment l'accès à vos données ou leur effacement auprès du presbytère.")
    return (avis +
            f'<form class="question"{action}><fieldset{dis}>'
            '<div style="display:grid;gap:1rem">'
            '<label for="f-prenom">Prénom<input id="f-prenom" name="prenom" autocomplete="given-name" required></label>'
            '<label for="f-contact">Courriel ou téléphone, pour vous répondre'
            '<input id="f-contact" name="contact" autocomplete="email" required></label>'
            '<label for="f-objet">Votre demande<select id="f-objet" name="objet">'
            '<option>Une question sur la foi ou sur l\'Église</option>'
            '<option>Demander un sacrement (baptême, confirmation, mariage, réconciliation)</option>'
            '<option>Rencontrer un prêtre</option>'
            '<option>Rejoindre un service ou un groupe de la paroisse</option>'
            '<option>Autre demande</option></select></label>'
            '<label for="f-message">Votre message<textarea id="f-message" name="message" required></textarea></label>'
            + (('<label class="case" for="f-rappel"><input type="checkbox" id="f-rappel" name="rappel">'
                '<span>Je souhaite être rappelé par téléphone</span></label>'
                '<label for="f-tel">Téléphone, si vous souhaitez être rappelé'
                '<input id="f-tel" name="telephone" type="tel" autocomplete="tel"></label>')
               if base["parametres"].get("proposer_rappel") else "") +
            '<label class="piege" for="f-site">Ne pas remplir<input id="f-site" name="_gotcha" tabindex="-1" autocomplete="off"></label>'
            '<label class="case" for="f-accord"><input type="checkbox" id="f-accord" name="accord" required>'
            "<span>J'accepte que ces informations soient utilisées par la paroisse pour répondre à ma demande.</span></label>"
            '<div><button class="bouton" type="submit">Envoyer</button></div>'
            '</div></fieldset></form>'
            f'<p class="rgpd">{rgpd}</p>')


def bloc_formulaire_question(base):
    f = base.get("formulaire_question", {})
    c = base["contact"]
    actif = f.get("actif")
    if actif and f.get("type") == "lien" and f.get("lien"):
        return (f'<p><a class="bouton" href="{e(f["lien"])}" target="_blank" rel="noopener">'
                "Poser ma question</a></p>")
    avis = "" if actif else (
        '<p class="avis">Formulaire en cours de mise en place : l\'envoi n\'est pas encore activé. '
        f'En attendant, l\'accueil du presbytère répond au {e(c["telephone"])}.</p>')
    action = f' action="{e(f["adresse_envoi"])}" method="post"' if actif and f.get("adresse_envoi") else ""
    dis = "" if actif else " disabled"
    themes = "".join(f"<option>{e(t)}</option>" for t in base.get("themes_questions", []))
    return (avis +
            f'<form class="question"{action}><fieldset{dis}>'
            '<div style="display:grid;gap:1rem">'
            '<label for="q-question">Votre question<textarea id="q-question" name="question" required></textarea></label>'
            f'<label for="q-theme">Thème, facultatif<select id="q-theme" name="theme"><option value="">Je ne sais pas</option>{themes}</select></label>'
            '<label for="q-mail">Courriel, facultatif : pour être prévenu de la réponse ou recevoir une réponse personnelle'
            '<input id="q-mail" name="email" type="email" autocomplete="email"></label>'
            '<label class="piege" for="q-site">Ne pas remplir<input id="q-site" name="_gotcha" tabindex="-1" autocomplete="off"></label>'
            '<div><button class="bouton" type="submit">Envoyer ma question</button></div>'
            '</div></fieldset></form>'
            '<p class="rgpd">Aucun nom n\'est demandé. Votre question est lue par un prêtre ou par l\'équipe d\'accueil ; '
            'si elle peut éclairer d\'autres personnes, elle est publiée sur cette page avec sa réponse, reformulée au besoin '
            'pour ne contenir aucun détail personnel. Une question très personnelle reçoit une réponse privée si vous avez '
            f'laissé votre courriel, et n\'est jamais publiée. Les messages reçus sont conservés {e(f.get("conservation", "six mois"))} au plus.</p>')


def page_questions(base, auj):
    qs = base.get("questions", [])
    note = base["parametres"].get("questions_note")
    note_html = f'<p class="avis">{e(note)}</p>' if note and any(q.get("statut") == "exemple" for q in qs) else ""
    themes = [t for t in base.get("themes_questions", []) if any(q["theme"] == t for q in qs)]
    themes += sorted({q["theme"] for q in qs} - set(themes))
    sommaire = " · ".join(f'<a href="#theme-{i}">{e(t)}</a>' for i, t in enumerate(themes))
    blocs = []
    for i, t in enumerate(themes):
        items = "".join(
            f'<details id="{e(q["id"])}"><summary>{e(q["question"])}</summary>'
            + "".join(f"<p>{e(par)}</p>" for par in q["reponse"].split("\n\n"))
            + "</details>"
            for q in qs if q["theme"] == t)
        blocs.append(f'<h2 id="theme-{i}">{e(t)}</h2><div class="faq">{items}</div>')
    corps = note_html + (f'<p class="sommaire">{sommaire}</p>' if sommaire else "") + "".join(blocs)
    return "\n".join([
        section("questions", "Vos questions",
                "Les questions que chacun peut se poser sur la foi, les sacrements et la vie de l'Église, "
                "avec les réponses de la paroisse. Vous pouvez poser la vôtre, sans donner votre nom.",
                corps, niveau=1),
        section("poser", "Poser une question", "", bloc_formulaire_question(base)),
    ])


# ---------------------------------------------------------------- pages

def page_accueil(base, auj):
    semaine = auj + dt.timedelta(days=7)
    deux = ('<div class="deux"><div><h2>Prochaines messes</h2>'
            f'{bloc_messes(base, auj, semaine)}<a class="voir" href="messes.html">Tous les horaires</a></div>'
            f'<div><h2>À venir</h2>{bloc_evenements(base, auj, 3)}'
            '<a class="voir" href="agenda.html">Tout l\'agenda</a></div></div>')
    return "\n".join([
        f'<section id="semaine"><div class="wrap">{deux}</div></section>',
        bloc_appel(base),
        section("annonces", "Annonces", "La vie de la paroisse en ce moment.",
                cartes(annonces_en_cours(base, auj))),
    ])


def page_messes(base, auj):
    return section("messes", "Messes et célébrations",
                   "Horaires des prochaines semaines, dans les églises de la paroisse.",
                   bloc_messes(base, auj) + note_maj(base), niveau=1)


def page_agenda(base, auj):
    return "\n".join([
        section("evenements", "Agenda",
                "Concerts, conférences, pèlerinages, fêtes et temps forts, ouverts à tous.",
                bloc_evenements(base, auj), niveau=1),
        section("annonces", "Annonces", "Rendez-vous réguliers et informations de la paroisse.",
                cartes(annonces_en_cours(base, auj))),
    ])


def page_vie(base, auj):
    return "\n".join(filter(None, [
        section("demarches", "Vie paroissiale",
                "Les démarches les plus fréquentes : l'accueil du presbytère oriente chaque demande.",
                cartes(base["demarches"], "demarches"), niveau=1),
        section("services", "Services et mouvements", "",
                cartes(base["vie_paroissiale"])),
        bloc_carnet(base),
    ]))


def page_paroisse(base, auj):
    pr = base["presentation"]
    lis = "".join(f'<li><b>{e(c)}</b><span>{e(base["lieux"].get(c, "").capitalize())}</span></li>'
                  for c in pr["clochers"])
    return section("paroisse", "La paroisse", e(pr["texte"]),
                   f'<h2>Les treize clochers</h2><ul class="clochers">{lis}</ul>', niveau=1)


def page_contact(base, auj):
    a = base["accueil_foi"]
    return "\n".join([
        section("contact", "Contact et accueil", "", bloc_coordonnees(base), niveau=1),
        section("question", e(a["titre"]), e(a["texte"]), bloc_formulaire(base)),
    ])


CONSTRUCTEURS = {
    "index.html": (page_accueil, "Horaires des messes, agenda et vie de la paroisse Saint-Aubin de l'Illet, treize clochers autour de Saint-Aubin-d'Aubigné (diocèse de Rennes)."),
    "messes.html": (page_messes, "Horaires des messes dans les treize églises de la paroisse Saint-Aubin de l'Illet : Saint-Aubin-d'Aubigné, Sens-de-Bretagne, Mouazé, Feins, Gahard et les autres clochers."),
    "agenda.html": (page_agenda, "Événements, concerts, temps forts et annonces de la paroisse Saint-Aubin de l'Illet."),
    "vie-paroissiale.html": (page_vie, "Baptême, mariage, obsèques, intentions de messe, services et carnet de la paroisse Saint-Aubin de l'Illet."),
    "paroisse.html": (page_paroisse, "Présentation de la paroisse Saint-Aubin de l'Illet et de ses treize clochers, doyenné de la Trinité, diocèse de Rennes."),
    "questions.html": (page_questions, "Questions fréquentes sur la foi, le baptême, la confession, le mariage et la messe : posez votre question à la paroisse Saint-Aubin de l'Illet, même de façon anonyme."),
    "contact.html": (page_contact, "Accueil du presbytère de Saint-Aubin-d'Aubigné et formulaire pour poser une question sur la foi ou être accueilli."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--purger", action="store_true")
    a = ap.parse_args()
    auj = d(a.date) if a.date else dt.datetime.now(ZoneInfo("Europe/Paris")).date()

    base = json.loads(DONNEES.read_text(encoding="utf-8"))
    base.setdefault("evenements", [])
    if a.purger:
        purger(base, auj)
        DONNEES.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    modele = MODELE.read_text(encoding="utf-8")
    bandeau = base["parametres"].get("bandeau")
    bandeau_html = f'<div class="demo">{e(bandeau)}</div>' if bandeau else ""
    nom = "Paroisse Saint-Aubin de l'Illet"
    for fichier, libelle in PAGES:
        fonction, description = CONSTRUCTEURS[fichier]
        nav = "\n".join(
            f'    <a href="{f}"' + (' aria-current="page"' if f == fichier else "") + f">{l}</a>"
            for f, l in PAGES)
        if fichier == "index.html":
            entete = ('<header class="hero"><div class="wrap">'
                      '<div class="eyebrow">Diocèse de Rennes · Doyenné de la Trinité</div>'
                      f'<h1>{e(nom)}</h1><p>{e(base["presentation"]["accroche"])}</p></div></header>')
            titre = nom
        else:
            entete = ('<header class="hero petit"><div class="wrap">'
                      '<div class="eyebrow">Diocèse de Rennes · Doyenné de la Trinité</div>'
                      f'<a class="site" href="index.html">{e(nom)}</a></div></header>')
            titre = f"{libelle} · {nom}"
        page = (modele.replace("{{TITRE}}", e(titre))
                      .replace("{{DESCRIPTION}}", e(description))
                      .replace("{{BANDEAU}}", bandeau_html)
                      .replace("{{ENTETE}}", entete)
                      .replace("{{NAV}}", nav)
                      .replace("{{CONTENU}}", fonction(base, auj))
                      .replace("{{DATE_MAJ}}", e(date_longue(base["mise_a_jour"]["date"], False, True))))
        (RACINE / fichier).write_text(page, encoding="utf-8")
    print(f"{len(PAGES)} pages construites, référence {auj}")


if __name__ == "__main__":
    sys.exit(main())
