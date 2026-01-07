from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import random
import json
import os
import logging # LOGOLÁS IMPORTÁLÁSA

Base = declarative_base()

# ... (A modellek: Faction, Player, Game, GameParticipant maradjanak ugyanazok!) ...
class Faction(Base):
    __tablename__ = 'factions'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    active = Column(Boolean, default=True)

class Game(Base):
    __tablename__ = 'games'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.now)
    participants = relationship("GameParticipant", back_populates="game")
    is_active = Column(Boolean, default=True)
    winner_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    winner = relationship("Player", foreign_keys=[winner_id])

class GameParticipant(Base):
    __tablename__ = 'game_participants'
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    player_id = Column(Integer, ForeignKey('players.id'))
    selected_faction_id = Column(Integer, ForeignKey('factions.id'), nullable=True)
    drafted_factions_json = Column(String)
    game = relationship("Game", back_populates="participants")
    player = relationship("Player")
    selected_faction = relationship("Faction")

# --- MOTOR LÉTREHOZÁSA JAVÍTOTT ÚTVONALLAL ---
# Megkeressük, hol van EZ a fájl (db_manager.py) a gépen:
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Hozzáfűzzük az adatbázis nevét:
db_path = os.path.join(BASE_DIR, 'ti_manager.db')

logging.info(f"DB: Adatbázis útvonala: {db_path}")

try:
    # Fontos: 'sqlite:///' után jön a teljes útvonal
    engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    logging.info("DB: Motor és táblák rendben.")
except Exception as e:
    logging.critical(f"DB: HIBA A MOTOR LÉTREHOZÁSAKOR: {e}")

class TIManager:
    def __init__(self):
        logging.info("DB Manager: Új session nyitása...")
        self.session = Session()
        self._init_factions()
        self._check_schema_updates()
        logging.info("DB Manager: Kész.")

    def _init_factions(self):
        logging.info("DB: Fajok ellenőrzése és frissítése...")

        # A teljes lista, benne a Keleres-szel
        fajok = [
            "The Arborec", "The Barony of Letnev", "The Clan of Saar", "The Embers of Muaat",
            "The Emirates of Hacan", "The Federation of Sol", "The Ghosts of Creuss", "The L1Z1X Mindnet",
            "The Mentak Coalition", "The Naalu Collective", "The Nekro Virus", "The Sardakk N'orr",
            "The Universities of Jol-Nar", "The Winnu", "The Xxcha Kingdom", "The Yin Brotherhood",
            "The Yssaril Tribes",
            "The Argent Flight", "The Empyrean", "The Mahact Gene-Sorcerers", "The Naaz-Rokha Alliance",
            "The Nomad", "The Titans of Ul", "The Vuil'raith Cabal",
            "The Council Keleres"  # <--- ITT AZ ÚJ FAJ!
        ]

        # Végigmegyünk a listán, és csak azt adjuk hozzá, ami még NINCS az adatbázisban
        added_count = 0
        for f_nev in fajok:
            # Megnézzük, létezik-e már ez a név
            exists = self.session.query(Faction).filter_by(name=f_nev).first()

            if not exists:
                logging.info(f"DB: Új faj hozzáadása: {f_nev}")
                self.session.add(Faction(name=f_nev))
                added_count += 1

        if added_count > 0:
            self.session.commit()
            logging.info(f"DB: {added_count} új faj sikeresen mentve.")
        else:
            logging.info("DB: Minden faj naprakész.")

    # ... (A többi függvény maradhat a régiben, de a `add_player` és `start_draft` logolása már benne van) ...
    def add_player(self, name):
        if not self.session.query(Player).filter_by(name=name).first():
            self.session.add(Player(name=name))
            self.session.commit()
            return True
        return False

    def get_all_players(self):
        logging.info("DB: get_all_players hívás...")
        res = self.session.query(Player).filter_by(active=True).all()
        logging.info(f"DB: {len(res)} játékos találva.")
        return res

    def get_all_games(self):
        logging.info("DB: get_all_games hívás...")
        return self.session.query(Game).order_by(Game.date.desc()).all()

    def save_player_choice(self, participant_id, faction_id):
        part = self.session.query(GameParticipant).get(participant_id)
        if part:
            part.selected_faction_id = faction_id
            self.session.commit()

    # --- ÚJ CRUD FUNKCIÓK ---

    def delete_game(self, game_id):
        """Teljes játék törlése résztvevőkkel együtt"""
        game = self.session.query(Game).get(game_id)
        if game:
            logging.info(f"DB: Játék törlése (ID: {game_id})")
            # Először a résztvevőket töröljük (Cascading delete kézileg, a biztonság kedvéért)
            for p in game.participants:
                self.session.delete(p)
            self.session.delete(game)
            self.session.commit()
            return True
        return False

    def create_manual_game(self, date_obj, player_faction_pairs):
        """
        Kézi játék létrehozása.
        player_faction_pairs: lista tuple-ökből -> [(player_id, faction_id), ...]
        """
        logging.info(f"DB: Kézi játék mentése {len(player_faction_pairs)} fővel...")

        # 1. Játék létrehozása (automatikusan LEZÁRT / nem aktív)
        new_game = Game(date=date_obj, is_active=False)
        self.session.add(new_game)
        self.session.flush() # Hogy kapjon ID-t

        # 2. Résztvevők hozzáadása
        for p_id, f_id in player_faction_pairs:
            part = GameParticipant(
                game_id=new_game.id,
                player_id=p_id,
                selected_faction_id=f_id,
                drafted_factions_json=None # Kézi hozzáadásnál nincs draft history
            )
            self.session.add(part)

        self.session.commit()
        return True
    def _check_schema_updates(self):
        """Megnézi, hogy létezik-e a winner_id oszlop, és ha nem, hozzáadja."""
        try:
            # Megpróbáljuk lekérni a games táblát, hátha hibát dob
            self.session.execute(text("SELECT winner_id FROM games LIMIT 1"))
        except Exception:
            logging.info("DB: 'winner_id' oszlop hiányzik -> Migráció indítása...")
            try:
                # SQLite parancs az új oszlop hozzáadására
                self.session.get_bind().execute(text("ALTER TABLE games ADD COLUMN winner_id INTEGER REFERENCES players(id)"))
                self.session.commit()
                logging.info("DB: Migráció sikeres! (winner_id hozzáadva)")
            except Exception as e:
                logging.error(f"DB: Migráció sikertelen: {e}")

    def set_game_winner(self, game_id, player_id):
        game = self.session.query(Game).get(game_id)
        if game:
            # Ha ugyanazt küldjük, aki már nyert, akkor "kikapcsoljuk" (toggle)
            if game.winner_id == player_id:
                game.winner_id = None
                logging.info(f"DB: Győztes törölve a meccsről (ID: {game_id})")
            else:
                game.winner_id = player_id
                logging.info(f"DB: Új győztes beállítva (Game: {game_id} -> Player: {player_id})")

            self.session.commit()
            return True
        return False
    def start_new_game_draft(self, player_ids):
        # ---------------------------------------------------------
        # 0. LÉPÉS: ELŐKÉSZÜLETEK
        # ---------------------------------------------------------
        all_factions = self.session.query(Faction).all()
        faction_map = {f.id: f.name for f in all_factions}

        # ---------------------------------------------------------
        # 1. LÉPÉS: TAKARÍTÁS (Anti-Spam)
        # ---------------------------------------------------------
        absolute_last_game = self.session.query(Game).order_by(Game.date.desc()).first()

        if absolute_last_game and absolute_last_game.is_active:
            has_selection = False
            for p in absolute_last_game.participants:
                if p.selected_faction_id:
                    has_selection = True
                    break

            if not has_selection:
                logging.info(f"Takarítás: Előző, félbehagyott draft (Game ID: {absolute_last_game.id}) törlése...")
                for p in absolute_last_game.participants:
                    self.session.delete(p)
                self.session.delete(absolute_last_game)
                self.session.commit()

        # ---------------------------------------------------------
        # 2. LÉPÉS: GLOBÁLIS TILTÁS (History legutolsó meccs)
        # ---------------------------------------------------------
        last_finished_game = self.session.query(Game).filter_by(is_active=False).order_by(Game.date.desc()).first()

        global_ban_ids = set()

        if last_finished_game:
            for p in last_finished_game.participants:
                if p.selected_faction_id:
                    global_ban_ids.add(p.selected_faction_id)

            if global_ban_ids:
                ban_names = [faction_map.get(fid, str(fid)) for fid in global_ban_ids]
                logging.info(f"GLOBÁLIS TILTÁS (Előző meccs faja): {', '.join(ban_names)}")

        # ---------------------------------------------------------
        # 3. LÉPÉS: SORSOLÁS INDÍTÁSA
        # ---------------------------------------------------------
        logging.info("========================================")
        logging.info(f"ÚJ SORSOLÁS INDUL {len(player_ids)} JÁTÉKOSSAL")
        logging.info("========================================")

        new_game = Game()
        self.session.add(new_game)
        self.session.flush()

        draft_results = []
        session_drafted_ids = set()

        random_player_ids = list(player_ids)
        random.shuffle(random_player_ids)

        for p_id in random_player_ids:
            player = self.session.query(Player).get(p_id)
            logging.info(f"--- Feldolgozás: [{player.name}] ---")

            # SZŰRÉS 1: Amit TÉNYLEGESEN VÁLASZTOTT (Utolsó 2 meccs)
            last_2_matches = self.session.query(GameParticipant)\
                .filter_by(player_id=p_id)\
                .join(Game)\
                .filter(Game.is_active == False)\
                .order_by(Game.date.desc())\
                .limit(2)\
                .all()

            played_ids = {h.selected_faction_id for h in last_2_matches if h.selected_faction_id}

            # SZŰRÉS 2: Amit FELKÍNÁLTAK NEKI (Sorsolás history)
            # --- ITT A VÁLTOZÁS: Limit 3 helyett Limit 2 ---
            last_2_drafts = self.session.query(GameParticipant)\
                .filter_by(player_id=p_id)\
                .join(Game)\
                .order_by(Game.date.desc())\
                .limit(2)\
                .all()

            recent_drafted_ids = set()
            for match in last_2_drafts:
                if match.drafted_factions_json:
                    try:
                        ids = json.loads(match.drafted_factions_json)
                        recent_drafted_ids.update(ids)
                    except:
                        pass

            # Logolás
            if played_ids:
                names = [faction_map.get(i, str(i)) for i in played_ids]
                logging.info(f"   Tiltva (Utolsó 2 választása): {', '.join(names)}")

            if recent_drafted_ids:
                names = [faction_map.get(i, str(i)) for i in recent_drafted_ids]
                logging.info(f"   Tiltva (Utolsó 2 sorsoláson látta): {', '.join(names)}")


            # KALAP ÖSSZEÁLLÍTÁSA
            available_pool = [
                f for f in all_factions
                if f.id not in played_ids            # Utolsó 2 választás tiltva
                and f.id not in recent_drafted_ids   # Utolsó 2 kínálat (6 faj) tiltva
                and f.id not in session_drafted_ids  # Mostani körben másnak adott tiltva
                and f.id not in global_ban_ids       # Előző meccs összes faja tiltva
            ]

            logging.info(f"   Ideális választék mérete: {len(available_pool)}")

            # --- VÉSZTERVEK (Lazított sorrend) ---

            # 1. VÉSZTERV: Elengedjük a "Kínálatban volt" (Draft History) tiltást.
            # Ez a legkevésbé fontos, ettől még nem lesz ismétlődő a játék.
            if len(available_pool) < 3:
                logging.warning("   ! Kevés a faj -> 'Utolsó 2 sorsolásban felkínált' szabály feloldása.")
                available_pool = [
                    f for f in all_factions
                    if f.id not in played_ids             # Még mindig védjük amit játszott
                    and f.id not in session_drafted_ids
                    and f.id not in global_ban_ids        # Még mindig védjük az előző meccset
                    # recent_drafted_ids TÖRÖLVE
                ]

            # 2. VÉSZTERV: Elengedjük az ELŐZŐ MECCS (Global Ban) tiltását.
            if len(available_pool) < 3:
                logging.warning("   !! Még mindig kevés -> 'Előző history játék fajai' tiltás feloldása.")
                available_pool = [
                    f for f in all_factions
                    if f.id not in played_ids             # Még mindig védjük amit játszott
                    and f.id not in session_drafted_ids
                    # global_ban_ids TÖRÖLVE
                ]

            # 3. VÉSZTERV: Elengedjük a "SAJÁT UTOLSÓ 2 VÁLASZTÁS" tiltását.
            if len(available_pool) < 3:
                logging.warning("   !!! Még mindig kevés -> 'Utolsó 2 meccsen választott' szabály feloldása.")
                available_pool = [
                    f for f in all_factions
                    if f.id not in session_drafted_ids    # Csak az egyediség számít
                ]

            # 4. VÉGSŐ KÉTSÉGBEESÉS
            if len(available_pool) < 3:
                 logging.error("   !!!! KRITIKUS: Csak a 'mostani egyediség' számít.")
                 available_pool = [f for f in all_factions if f.id not in session_drafted_ids]

                 if len(available_pool) < 3:
                     logging.critical("   !!!!! VÉGZETES HIBA: Nincs elég faj a pakliban!")
                     available_pool = all_factions

            # HÚZÁS
            drawn_factions = random.sample(available_pool, 3)
            drawn_ids = [f.id for f in drawn_factions]
            drawn_names = [f.name for f in drawn_factions]

            logging.info(f"   >>> KISORSOLVA: {', '.join(drawn_names)}")

            session_drafted_ids.update(drawn_ids)

            participant = GameParticipant(
                game_id=new_game.id,
                player_id=p_id,
                drafted_factions_json=json.dumps(drawn_ids),
                selected_faction_id=None
            )
            self.session.add(participant)
            self.session.flush()

            draft_results.append({
                "player_name": player.name,
                "participant_id": participant.id,
                "options": drawn_factions
            })

        self.session.commit()
        logging.info("Sorsolás befejezve.")
        logging.info("========================================")

        draft_results.sort(key=lambda x: x["player_name"])
        return draft_results