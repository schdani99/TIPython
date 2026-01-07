from flask import Flask, render_template, request, redirect, url_for, flash
from db_manager import TIManager, Faction, GameParticipant
import logging
import sys
import json
import re
import os
from datetime import datetime

# --- 1. ÚTVONALAK BEÁLLÍTÁSA (Hogy a szerver megtalálja a fájlokat) ---
# Megkeressük, hol van EZ a fájl (app.py) a szerveren:
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Összerakjuk a Log fájl teljes útvonalát:
# Ez így pl: /home/schdani/mysite/ti_manager.log lesz
LOG_PATH = os.path.join(BASE_DIR, 'ti_manager.log')

# --- 2. LOGOLÁS BEÁLLÍTÁSA ---
# Először törlünk minden korábbi log beállítást (hogy ne akadjon össze a rendszerrel)
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    handlers=[
        # Itt használjuk a TELJES útvonalat:
        logging.FileHandler(LOG_PATH, encoding='utf-8'),

        # A konzolra írást (sys.stderr) meghagyjuk a hibakereséshez:
        logging.StreamHandler(sys.stderr)
    ]
)

app = Flask(__name__)
app.secret_key = 'szupertitkos_kulcs_ti4'


# ... (innen lefelé minden maradhat a régiben)

# Adatbázis indítása
logging.info("--- APP INDULÁSA... ---")
db = TIManager()

@app.route('/set_winner/<int:game_id>/<int:player_id>')
def set_winner(game_id, player_id):
    db.set_game_winner(game_id, player_id)
    # Nem kell flash üzenet, mert zavaró lenne minden kattintásnál,
    # a vizuális visszajelzés (arany trófea) elég lesz.
    return redirect(url_for('history'))

@app.route('/delete_game/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    if db.delete_game(game_id):
        flash("Meccs sikeresen törölve!", "success")
    else:
        flash("Hiba történt a törléskor.", "error")
    return redirect(url_for('history'))

@app.route('/add_manual_game', methods=['POST'])
def add_manual_game():
    try:
        # 1. Dátum feldolgozása
        date_str = request.form.get('game_date')
        if date_str:
            game_date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            game_date = datetime.now()

        # 2. Játékosok és fajok összepárosítása
        # A formból listákat kapunk: player_1, faction_1, player_2, faction_2...
        player_faction_pairs = []

        # Feltételezzük, hogy max 8 sort küldtünk (a HTML-ben ennyit rakunk majd)
        for i in range(1, 9):
            p_id = request.form.get(f'player_{i}')
            f_id = request.form.get(f'faction_{i}')

            # Csak akkor mentjük, ha mindkettő ki van töltve (nem üres)
            if p_id and f_id and p_id != "" and f_id != "":
                player_faction_pairs.append((int(p_id), int(f_id)))

        if len(player_faction_pairs) < 3:
            flash("Legalább 3 játékost rögzítened kell!", "error")
        else:
            db.create_manual_game(game_date, player_faction_pairs)
            flash("Kézi meccs sikeresen hozzáadva!", "success")

    except Exception as e:
        flash(f"Hiba történt: {e}", "error")
        logging.error(f"Manual Add Error: {e}")

    return redirect(url_for('history'))

@app.template_filter('slugify_faction')
def slugify_faction(name):
    """
    Átalakítja a faj nevét a fájlneved formátumára.
    Pl.: "The Federation of Sol" -> "the_federation_of_sol"
    """
    if not name: return ""
    s = name.lower()
    # Kivesz minden speciális karaktert (kötőjel, aposztróf), csak betű és szám marad
    s = re.sub(r'[^a-z0-9\s]', '', s)
    # A szóközöket alulvonásra cseréli
    s = s.replace(' ', '_')
    return s

@app.route('/')
def index():
    # 1. Lekérjük a játékokat
    games = db.get_all_games()
    players = db.get_all_players()

    # 2. Megnézzük, hogy a felhasználó kérte-e KÉNYSZERÍTVE a menüt
    # (Ha a link végén ott van, hogy ?force=1, akkor nem irányítunk át)
    force_show = request.args.get('force')

    # 3. Az Átirányítás Logika
    # Ha NINCS kényszerítés ÉS VAN aktív játék -> Irány a Draft!
    if not force_show and games and games[0].is_active:
        return redirect(url_for('draft_view'))

    # Egyébként (vagy nincs játék, vagy kértük a menüt) -> Főoldal betöltése
    return render_template('index.html', players=players, games=games)
@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form.get('name')
    if name:
        logging.info(f"Kérés: Új játékos hozzáadása -> {name}")
        if db.add_player(name):
            flash(f"{name} hozzáadva!", "success")
        else:
            flash("Ez a játékos már létezik!", "error")
    return redirect(url_for('index'))

@app.route('/start_draft', methods=['POST'])
def start_draft():
    player_ids = request.form.getlist('player_ids')

    if len(player_ids) < 3:
        flash("Legalább 3 játékost válassz ki!", "error")
        return redirect(url_for('index'))

    player_ids_int = [int(pid) for pid in player_ids]

    logging.info(f"Kérés: Új SORSOLÁS indítása {len(player_ids_int)} fővel...")
    db.start_new_game_draft(player_ids_int)

    flash("Új sorsolás elindult!", "success")
    return redirect(url_for('draft_view'))

@app.route('/draft')
def draft_view():
    games = db.get_all_games()

    # Ha nincs játék, VAGY a legutolsó játék már le van zárva (nem aktív)
    # Akkor eldobjuk a felhasználót a főoldalra.
    if not games or not games[0].is_active:
        return redirect(url_for('index'))

    current_game = games[0]

    # --- JAVÍTÁS ---
    # Innen KIVETTÜK azt az ellenőrzést, ami visszadobott a főoldalra,
    # ha már mindenki választott.
    # Mostantól a Draft oldal mindig elérhető marad a legutolsó játékra,
    # amíg nem indítasz egy teljesen újat.

    logging.info(f"    Játék betöltve (ID: {current_game.id})")

    participants_data = []
    all_factions = {f.id: f for f in db.session.query(Faction).all()}

    for p in current_game.participants:
        options = []
        if p.drafted_factions_json:
            try:
                drafted_ids = json.loads(p.drafted_factions_json)
                for fid in drafted_ids:
                    f = all_factions.get(fid)
                    if f: options.append(f)
            except:
                pass

        participants_data.append({
            "id": p.id,
            "player_name": p.player.name,
            "options": options,
            "selected_faction_id": p.selected_faction_id,
            "selected_faction_name": p.selected_faction.name if p.selected_faction else None
        })

    participants_data.sort(key=lambda x: x["player_name"])
    return render_template('draft.html', participants=participants_data)

@app.route('/select_faction/<int:participant_id>/<int:faction_id>')
def select_faction(participant_id, faction_id):
    # EZT LÁTNI AKARJUK: Ki mit választott
    logging.info(f">>> KATTINTÁS: Participant[{participant_id}] választotta: FactionID[{faction_id}]")
    db.save_player_choice(participant_id, faction_id)
    flash("Választás mentve!", "success")
    return redirect(url_for('draft_view'))

@app.route('/history')
def history():
    # Csak a lezárt játékok
    all_games = db.get_all_games()
    finished_games = [g for g in all_games if not g.is_active]

    # --- ÚJ: Lekérjük az adatokat a kézi hozzáadáshoz ---
    players = db.get_all_players()
    factions = db.session.query(Faction).order_by(Faction.name).all()

    return render_template('history.html', games=finished_games, players=players, factions=factions)


@app.route('/finalize_game')
def finalize_game():
    logging.info(">>> Játék véglegesítése és tisztítása...")

    # Lekérjük a legutolsó (éppen zajló) játékot
    games = db.get_all_games()
    if not games:
        return redirect(url_for('index'))

    current_game = games[0]
    participants_to_remove = []
    active_count = 0

    # 1. LÉPÉS: Megnézzük, ki az, aki NEM választott
    for p in current_game.participants:
        if p.selected_faction_id is None:
            logging.info(f"    Törlésre jelölve (nem választott): {p.player.name}")
            participants_to_remove.append(p)
        else:
            active_count += 1

    # 2. LÉPÉS: Töröljük a lusta játékosokat az adatbázisból
    for p in participants_to_remove:
        db.session.delete(p)

    # 3. LÉPÉS: Ha senki nem maradt, töröljük az egész játékot
    if active_count == 0:
        logging.info("    Senki nem választott -> A teljes játék törlése.")
        db.session.delete(current_game)
        db.session.commit()
        flash("A játék törölve lett, mert senki nem választott fajt.", "warning")
        return redirect(url_for('index'))

    # --- ÚJ RÉSZ: JÁTÉK LEZÁRÁSA ---
    # Ez tünteti el a Draft oldalról!
    current_game.is_active = False

    # 4. LÉPÉS: Mentés
    db.session.commit()

    flash(f"Játék rögzítve! ({active_count} játékos választott)", "success")
    return redirect(url_for('history'))


if __name__ == '__main__':
    # use_reloader=False FONTOS, hogy ne duplázza a logokat és ne akadjon össze
    print("Szerver indítása... Figyeld a logokat!")
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)