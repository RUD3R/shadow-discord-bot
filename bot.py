import discord
from discord import app_commands
from discord.ext import commands
import re
import json
import os

GUILD_ID = 1405260760254251200  # Twoje ID serwera Discord

intents = discord.Intents.default()
intents.message_content = True  # Wymagane do czytania wiadomości (1, -, -10 itp.) w wątku

bot = commands.Bot(command_prefix="!", intents=intents)

AKTYWNOSC_FILE = "aktywnosc.json"
EKONOMIA_FILE = "ekonomia.json"

# --- OBSŁUGA PLIKÓW DANYCH ---
def nczytaj_json(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def zapisz_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

active_contents = {}

# -------------------------------------------------------------------
# FORMULARZ (MODAL) DLA TWORZENIA CONTENTU
# -------------------------------------------------------------------
class ContentModal(discord.ui.Modal, title="Tworzenie nowego contentu"):
    content_title = discord.ui.TextInput(
        label="Tytuł contentu / Opis",
        placeholder="np. Static Dungeon BZ 20:00 (1300+ IP)",
        required=True
    )
    
    roles_input = discord.ui.TextInput(
        label="Lista ról (każda rola w nowej linii)",
        style=discord.TextStyle.paragraph,
        placeholder="1. Main Tank\n2. Off Tank\n3. Holy Healer\n4. DPS",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_lines = self.roles_input.value.splitlines()
        roles_list = []
        
        for line in raw_lines:
            line = line.strip()
            if line:
                clean_role = re.sub(r"^\d+[\.\)]\s*", "", line)
                roles_list.append(clean_role)
        
        if not roles_list:
            await interaction.response.send_message("❌ Musisz podać przynajmniej jedną rolę!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⚔️ {self.content_title.value}",
            color=discord.Color.gold()
        )
        
        positions_text = ""
        signups_dict = {}
        for idx, role in enumerate(roles_list, 1):
            positions_text += f"`{idx}.` **{role}**: *Wolne*\n"
            signups_dict[idx] = None
            
        embed.add_field(name="📋 Lista pozycji:", value=positions_text, inline=False)
        
        instructions = (
            "**Jak się zapisać:**\n"
            "• Wpisz numer pozycji, aby się zapisać (np. `9` aby zająć pozycję nr 9)\n"
            "• Wpisz `-` aby anulować swój zapis\n\n"
            "**Komendy administratora / organizatora:**\n"
            "• `-NUMER` - Usuń gracza z danej pozycji (np. `-10`)\n"
            "• `NUMER @osoba` - Zapisz innego gracza (np. `10 @User`)\n"
            "• **`/edytuj_content`** - Edytuj tytuł i role w tym wątku\n"
            "• **`/split kwota: 2000000`** - Podziel silver i dodaj punkty do kont graczy\n"
            "• **`/zakoncz`** - Zakończ event bez podziału silvera (tylko +1 aktywność)"
        )
        embed.add_field(name="ℹ️ Instrukcja", value=instructions, inline=False)
        embed.set_footer(text=f"Organizator: {interaction.user.display_name}")

        await interaction.response.send_message("Tworzenie contentu...", ephemeral=True)
        
        main_msg = await interaction.channel.send(embed=embed)
        thread = await main_msg.create_thread(name=f"Zapisy: {self.content_title.value[:50]}")
        
        active_contents[thread.id] = {
            "title": self.content_title.value,
            "roles": roles_list,
            "signups": signups_dict,
            "main_msg_id": main_msg.id,
            "channel_id": interaction.channel_id,
            "organizer_id": interaction.user.id
        }

        await thread.send(f"Wątek do zapisów został otwarty! Wpisz numer pozycji (1-{len(roles_list)}), aby się zapisać.")

# -------------------------------------------------------------------
# FORMULARZ (MODAL) DLA EDYCJI CONTENTU
# -------------------------------------------------------------------
class EditContentModal(discord.ui.Modal, title="Edycja contentu"):
    def __init__(self, current_title, current_roles):
        super().__init__()
        
        self.content_title = discord.ui.TextInput(
            label="Tytuł contentu / Opis",
            default=current_title,
            required=True
        )
        self.add_item(self.content_title)

        roles_str = "\n".join([f"{idx}. {r}" for idx, r in enumerate(current_roles, 1)])
        self.roles_input = discord.ui.TextInput(
            label="Lista ról (każda rola w nowej linii)",
            style=discord.TextStyle.paragraph,
            default=roles_str,
            required=True
        )
        self.add_item(self.roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        thread_id = interaction.channel_id
        if thread_id not in active_contents:
            await interaction.response.send_message("❌ Nie znaleziono aktywnego contentu dla tego wątku.", ephemeral=True)
            return

        data = active_contents[thread_id]

        raw_lines = self.roles_input.value.splitlines()
        new_roles_list = []
        for line in raw_lines:
            line = line.strip()
            if line:
                clean_role = re.sub(r"^\d+[\.\)]\s*", "", line)
                new_roles_list.append(clean_role)

        if not new_roles_list:
            await interaction.response.send_message("❌ Musisz podać przynajmniej jedną rolę!", ephemeral=True)
            return

        new_signups = {}
        old_signups = data["signups"]
        for idx in range(1, len(new_roles_list) + 1):
            new_signups[idx] = old_signups.get(idx, None)

        data["title"] = self.content_title.value
        data["roles"] = new_roles_list
        data["signups"] = new_signups

        try:
            await interaction.channel.edit(name=f"Zapisy: {self.content_title.value[:50]}")
        except Exception:
            pass

        await update_content_embed(thread_id)
        await interaction.response.send_message("✅ Content został pomyślnie zaktualizowany!")

# -------------------------------------------------------------------
# REJESTRACJA KOMEND SLASH
# -------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Zalogowano jako {bot.user.name}!")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"✅ Zsynchronizowano {len(synced)} komend(y) slash dla serwera {GUILD_ID}!")
    except Exception as e:
        print(f"❌ Błąd synchronizacji komend: {e}")

@bot.tree.command(name="content", description="Stwórz nowy content z zapisami w wątku")
async def content_command(interaction: discord.Interaction):
    await interaction.response.send_modal(ContentModal())

@bot.tree.command(name="edytuj_content", description="Edytuj tytuł i role w aktywnym wątku contentu")
async def edytuj_content_command(interaction: discord.Interaction):
    thread_id = interaction.channel_id
    if thread_id not in active_contents:
        await interaction.response.send_message("❌ Tej komendy można użyć tylko w aktywnym wątku zapisów!", ephemeral=True)
        return

    data = active_contents[thread_id]
    is_organizer = interaction.user.id == data["organizer_id"]
    is_admin = interaction.user.guild_permissions.administrator

    if not (is_organizer or is_admin):
        await interaction.response.send_message("❌ Tylko organizator tego contentu lub administrator może go edytować!", ephemeral=True)
        return

    modal = EditContentModal(current_title=data["title"], current_roles=data["roles"])
    await interaction.response.send_modal(modal)

# --- KOMENDY EKONOMII DLA GRACZY ---

@bot.tree.command(name="konto", description="Sprawdź stan swojego konta silvera")
async def konto_command(interaction: discord.Interaction):
    ekonomia_db = nczytaj_json(EKONOMIA_FILE)
    user_id = str(interaction.user.id)
    saldo = ekonomia_db.get(user_id, 0)
    
    embed = discord.Embed(
        title="💰 STAN KONTA",
        description=f"**{interaction.user.display_name}**, Twoje saldo wynosi:\n\n🪙 **{saldo:,}** Silvera".replace(",", " "),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="daj_silver", description="Przekaż swój silver innemu graczowi")
@app_commands.describe(gracz="Gracz, któremu chcesz przekazać silver", kwota="Liczba silvera do przekazania")
async def daj_silver_command(interaction: discord.Interaction, gracz: discord.Member, kwota: int):
    if gracz.id == interaction.user.id:
        await interaction.response.send_message("❌ Nie możesz przekazać silvera samemu sobie!", ephemeral=True)
        return

    if gracz.bot:
        await interaction.response.send_message("❌ Nie możesz przekazać silvera botowi!", ephemeral=True)
        return

    if kwota <= 0:
        await interaction.response.send_message("❌ Kwota musi być większa niż 0!", ephemeral=True)
        return

    ekonomia_db = nczytaj_json(EKONOMIA_FILE)
    nadawca_id = str(interaction.user.id)
    odbiorca_id = str(gracz.id)

    saldo_nadawcy = ekonomia_db.get(nadawca_id, 0)

    if saldo_nadawcy < kwota:
        saldo_formatted = f"{saldo_nadawcy:,}".replace(",", " ")
        await interaction.response.send_message(f"❌ Nie masz wystarczająco środków na koncie! Twoje saldo to **{saldo_formatted}** Silvera.", ephemeral=True)
        return

    # Wykonujemy przelew
    ekonomia_db[nadawca_id] = saldo_nadawcy - kwota
    ekonomia_db[odbiorca_id] = ekonomia_db.get(odbiorca_id, 0) + kwota
    zapisz_json(EKONOMIA_FILE, ekonomia_db)

    kwota_formatted = f"{kwota:,}".replace(",", " ")
    await interaction.response.send_message(f"💸 {interaction.user.mention} przekazał **{kwota_formatted}** Silvera dla {gracz.mention}!")

# --- KOMENDY EKONOMII DLA ADMINÓW / SKARBNIKÓW ---

@bot.tree.command(name="dodaj_silver", description="Ręcznie dodaj silver graczowi")
@app_commands.checks.has_permissions(administrator=True)
async def dodaj_silver_command(interaction: discord.Interaction, gracz: discord.Member, kwota: int):
    if kwota <= 0:
        await interaction.response.send_message("❌ Kwota musi być większa niż 0!", ephemeral=True)
        return

    ekonomia_db = nczytaj_json(EKONOMIA_FILE)
    user_id = str(gracz.id)
    ekonomia_db[user_id] = ekonomia_db.get(user_id, 0) + kwota
    zapisz_json(EKONOMIA_FILE, ekonomia_db)

    nowe_saldo = ekonomia_db[user_id]
    kwota_formatted = f"{kwota:,}".replace(",", " ")
    nowe_saldo_formatted = f"{nowe_saldo:,}".replace(",", " ")
    
    await interaction.response.send_message(f"✅ Dodano **{kwota_formatted}** Silvera dla {gracz.mention}. Aktualny stan konta: **{nowe_saldo_formatted}** Silvera.")

@bot.tree.command(name="usun_silver", description="Ręcznie odejmij silver graczowi")
@app_commands.checks.has_permissions(administrator=True)
async def usun_silver_command(interaction: discord.Interaction, gracz: discord.Member, kwota: int):
    if kwota <= 0:
        await interaction.response.send_message("❌ Kwota musi być większa niż 0!", ephemeral=True)
        return

    ekonomia_db = nczytaj_json(EKONOMIA_FILE)
    user_id = str(gracz.id)
    obecne = ekonomia_db.get(user_id, 0)

    if obecne < kwota:
        await interaction.response.send_message(f"⚠️ Gracz posiada tylko {obecne:,} Silvera na koncie!".replace(",", " "), ephemeral=True)
        return

    ekonomia_db[user_id] = obecne - kwota
    zapisz_json(EKONOMIA_FILE, ekonomia_db)

    nowe_saldo = ekonomia_db[user_id]
    kwota_formatted = f"{kwota:,}".replace(",", " ")
    nowe_saldo_formatted = f"{nowe_saldo:,}".replace(",", " ")

    await interaction.response.send_message(f"💸 Pobrano **{kwota_formatted}** Silvera od {gracz.mention}. Aktualny stan konta: **{nowe_saldo_formatted}** Silvera.")

@bot.tree.command(name="skarbiec", description="Wyświetl finanse i stany kont graczy w gildii")
@app_commands.checks.has_permissions(administrator=True)
async def skarbiec_command(interaction: discord.Interaction):
    ekonomia_db = nczytaj_json(EKONOMIA_FILE)
    if not ekonomia_db:
        await interaction.response.send_message("Brak zapisanych danych finansowych.", ephemeral=True)
        return

    sorted_finances = sorted(ekonomia_db.items(), key=lambda item: item[1], reverse=True)
    
    text = ""
    total_silver = sum(ekonomia_db.values())

    for idx, (u_id, val) in enumerate(sorted_finances[:15], 1):
        val_formatted = f"{val:,}".replace(",", " ")
        text += f"`{idx}.` <@{u_id}> — **{val_formatted}** Silvera\n"

    total_formatted = f"{total_silver:,}".replace(",", " ")
    
    embed = discord.Embed(
        title="🏛️ SKARBIEC GILDII",
        description=f"**Łączna suma na kontach graczy:** {total_formatted} Silvera\n\n{text}",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

# --- KOMENDA SPLIT & ZAKOŃCZENIE CONTENTU ---

@bot.tree.command(name="split", description="Podziel podaną sumę silvera równo między obecnych graczy i zamknij wątek")
@app_commands.describe(kwota="Łączna kwota silvera zebrana z contentu")
async def split_command(interaction: discord.Interaction, kwota: int):
    thread_id = interaction.channel_id
    if thread_id not in active_contents:
        await interaction.response.send_message("❌ Tej komendy można użyć tylko w aktywnym wątku zapisów!", ephemeral=True)
        return

    data = active_contents[thread_id]
    is_organizer = interaction.user.id == data["organizer_id"]
    is_admin = interaction.user.guild_permissions.administrator

    if not (is_organizer or is_admin):
        await interaction.response.send_message("❌ Tylko organizator tego contentu lub administrator może go podzielić!", ephemeral=True)
        return

    if kwota <= 0:
        await interaction.response.send_message("❌ Kwota musi być większa niż 0!", ephemeral=True)
        return

    await interaction.response.defer()

    obecni_gracze = [u for u in data["signups"].values() if u is not None]
    
    if not obecni_gracze:
        await interaction.channel.send("⚠️ Żaden gracz nie był zapisany. Content zostaje zamknięty bez podziału.")
    else:
        liczba_graczy = len(obecni_gracze)
        na_glowe = kwota // liczba_graczy

        ekonomia_db = nczytaj_json(EKONOMIA_FILE)
        aktywnosc_db = nczytaj_json(AKTYWNOSC_FILE)

        lista_podsumowanie = ""

        for user_str in obecni_gracze:
            match = re.search(r"\d+", user_str)
            if match:
                u_id = match.group(0)
                ekonomia_db[u_id] = ekonomia_db.get(u_id, 0) + na_glowe
                aktywnosc_db[u_id] = aktywnosc_db.get(u_id, 0) + 1
                
                lista_podsumowanie += f"• <@{u_id}> ➔ +**{na_glowe:,}** Silvera\n".replace(",", " ")

        zapisz_json(EKONOMIA_FILE, ekonomia_db)
        zapisz_json(AKTYWNOSC_FILE, aktywnosc_db)

        kwota_formatted = f"{kwota:,}".replace(",", " ")
        na_glowe_formatted = f"{na_glowe:,}".replace(",", " ")

        embed_podsumowanie = discord.Embed(
            title="💰 PODZIAŁ SILVERA Z CONTENTU",
            description=(
                f"**Łączny łup:** {kwota_formatted} Silvera\n"
                f"**Liczba graczy:** {liczba_graczy}\n"
                f"**Wypłata na głowę:** **{na_glowe_formatted}** Silvera\n\n"
                f"**Zasilone konta graczy (+1 Aktywność):**\n{lista_podsumowanie}"
            ),
            color=discord.Color.gold()
        )
        await interaction.channel.send(embed=embed_podsumowanie)

    await update_content_embed(thread_id, is_finished=True)
    del active_contents[thread_id]
    
    await interaction.channel.send("🔒 Wątek zostaje zarchiwizowany.")
    await interaction.channel.edit(archived=True, locked=True)

# --- POZOSTAŁE KOMENDY AKTYWNOŚCI ---

@bot.tree.command(name="aktywnosc", description="Sprawdź swoją liczbę zaliczonych contentów")
async def aktywnosc_command(interaction: discord.Interaction):
    dane = nczytaj_json(AKTYWNOSC_FILE)
    user_id = str(interaction.user.id)
    punkty = dane.get(user_id, 0)
    await interaction.response.send_message(f"📊 **{interaction.user.display_name}**, masz na koncie **{punkty}** ukończonych contentów!", ephemeral=True)

@bot.tree.command(name="statystyki", description="Wyświetl ranking aktywności graczy w gildii")
@app_commands.checks.has_permissions(administrator=True)
async def statystyki_command(interaction: discord.Interaction):
    dane = nczytaj_json(AKTYWNOSC_FILE)
    if not dane:
        await interaction.response.send_message("Brak zapisanych danych o aktywności.", ephemeral=True)
        return

    sorted_players = sorted(dane.items(), key=lambda item: item[1], reverse=True)
    
    ranking_text = ""
    for idx, (u_id, count) in enumerate(sorted_players[:15], 1):
        ranking_text += f"`{idx}.` <@{u_id}> — **{count}** contentów\n"

    embed = discord.Embed(
        title="🏆 RANKING AKTYWNOŚCI GILDII",
        description=ranking_text,
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resetuj_aktywnosc", description="Resetuj aktywność graczowi lub całemu serwerowi")
@app_commands.checks.has_permissions(administrator=True)
async def resetuj_aktywnosc_command(interaction: discord.Interaction, gracz: discord.Member = None, wszyscy: bool = False):
    dane = nczytaj_json(AKTYWNOSC_FILE)

    if wszyscy:
        dane.clear()
        zapisz_json(AKTYWNOSC_FILE, dane)
        await interaction.response.send_message("🧹 **Zresetowano aktywność dla WSZYSTKICH graczy w gildii!**")
        return

    if gracz is not None:
        user_id = str(gracz.id)
        if user_id in dane:
            dane[user_id] = 0
            zapisz_json(AKTYWNOSC_FILE, dane)
            await interaction.response.send_message(f"🔄 Zresetowano punkty aktywności dla gracza {gracz.mention}.")
        else:
            await interaction.response.send_message(f"ℹ️ Gracz {gracz.mention} nie posiadał jeszcze żadnych punktów.", ephemeral=True)
        return

    await interaction.response.send_message("❌ Musisz oznaczyć gracza lub wybrać opcję `wszyscy: True`!", ephemeral=True)

@bot.tree.command(name="ustaw_aktywnosc", description="Ustaw konkretną liczbę punktów aktywności graczowi")
@app_commands.checks.has_permissions(administrator=True)
async def ustaw_aktywnosc_command(interaction: discord.Interaction, gracz: discord.Member, ilosc: int):
    dane = nczytaj_json(AKTYWNOSC_FILE)
    user_id = str(gracz.id)
    dane[user_id] = ilosc
    zapisz_json(AKTYWNOSC_FILE, dane)
    await interaction.response.send_message(f"✅ Ustawiono **{ilosc}** punktów aktywności dla gracza {gracz.mention}.")

@bot.tree.command(name="zakoncz", description="Zakończ content bez podziału silvera (tylko punkty aktywności)")
async def zakoncz_command(interaction: discord.Interaction):
    thread_id = interaction.channel_id
    if thread_id not in active_contents:
        await interaction.response.send_message("❌ Tej komendy można użyć tylko w aktywnym wątku zapisów!", ephemeral=True)
        return

    data = active_contents[thread_id]
    is_organizer = interaction.user.id == data["organizer_id"]
    is_admin = interaction.user.guild_permissions.administrator

    if not (is_organizer or is_admin):
        await interaction.response.send_message("❌ Tylko organizator tego contentu lub administrator może go zakończyć!", ephemeral=True)
        return

    await interaction.response.defer()

    obecni_gracze = [u for u in data["signups"].values() if u is not None]
    
    if not obecni_gracze:
        await interaction.channel.send("⚠️ Żaden gracz nie był zapisany. Content zostaje zamknięty bez przyznawania punktów.")
    else:
        aktywnosc_db = nczytaj_json(AKTYWNOSC_FILE)
        lista_obecnych_str = ""

        for user_str in obecni_gracze:
            match = re.search(r"\d+", user_str)
            if match:
                u_id = match.group(0)
                aktywnosc_db[u_id] = aktywnosc_db.get(u_id, 0) + 1
                lista_obecnych_str += f"• <@{u_id}>\n"

        zapisz_json(AKTYWNOSC_FILE, aktywnosc_db)

        embed_podsumowanie = discord.Embed(
            title="🎉 Content zakończony!",
            description=f"Każdy z poniższych graczy otrzymał **+1 do aktywności**:\n\n{lista_obecnych_str}",
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed_podsumowanie)

    await update_content_embed(thread_id, is_finished=True)
    del active_contents[thread_id]
    
    await interaction.channel.send("🔒 Wątek zostaje zarchiwizowany.")
    await interaction.channel.edit(archived=True, locked=True)

# -------------------------------------------------------------------
# AKTUALIZACJA GŁÓWNEGO EMBEDA
# -------------------------------------------------------------------
async def update_content_embed(thread_id, is_finished=False):
    data = active_contents.get(thread_id)
    if not data:
        return

    channel = bot.get_channel(data["channel_id"])
    if not channel:
        return

    try:
        main_msg = await channel.fetch_message(data["main_msg_id"])
    except:
        return

    roles_list = data["roles"]
    signups = data["signups"]

    positions_text = ""
    for idx, role in enumerate(roles_list, 1):
        user = signups.get(idx)
        status = user if user else "*Wolne*"
        positions_text += f"`{idx}.` **{role}**: {status}\n"

    embed = main_msg.embeds[0]
    embed.title = f"⚔️ {data['title']}"
    embed.set_field_at(0, name="📋 Lista pozycji:", value=positions_text, inline=False)
    
    if is_finished:
        embed.color = discord.Color.dark_grey()
        embed.title = f"🔴 [ZAKOŃCZONY] {data['title']}"

    await main_msg.edit(embed=embed)

# -------------------------------------------------------------------
# OBSŁUGA CZATU W WĄTKU (ZAPISY, ANULOWANIE, MODERACJA)
# -------------------------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id in active_contents:
        thread_id = message.channel.id
        data = active_contents[thread_id]
        text = message.content.strip()
        user_mention = message.author.mention
        num_roles = len(data["roles"])

        # 1. ANULOWANIE SWOJEGO ZAPISU ("-")
        if text == "-":
            removed = False
            for pos, user in data["signups"].items():
                if user == user_mention:
                    data["signups"][pos] = None
                    removed = True
            if removed:
                await update_content_embed(thread_id)
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")
            return

        # 2. ADMIN/ORGANIZATOR: USUNIĘCIE GRACZA Z POZYCJI (np. "-10")
        match_admin_remove = re.match(r"^-(\d+)$", text)
        if match_admin_remove:
            pos = int(match_admin_remove.group(1))
            if 1 <= pos <= num_roles:
                data["signups"][pos] = None
                await update_content_embed(thread_id)
                await message.add_reaction("🗑️")
            else:
                await message.add_reaction("❌")
            return

        # 3. ADMIN/ORGANIZATOR: ZAPISANIE KOGOŚ INNEGO (np. "10 @User")
        match_admin_add = re.match(r"^(\d+)\s+<@!?(\d+)>$", text)
        if match_admin_add:
            pos = int(match_admin_add.group(1))
            target_user_id = match_admin_add.group(2)
            target_mention = f"<@{target_user_id}>"

            if 1 <= pos <= num_roles:
                for p, u in data["signups"].items():
                    if u == target_mention:
                        data["signups"][p] = None
                
                data["signups"][pos] = target_mention
                await update_content_embed(thread_id)
                await message.add_reaction("👑")
            else:
                await message.add_reaction("❌")
            return

        # 4. ZAPIS NA POZYCJĘ (np. "1" lub "9")
        if text.isdigit():
            pos = int(text)
            if 1 <= pos <= num_roles:
                if data["signups"][pos] is not None and data["signups"][pos] != user_mention:
                    await message.channel.send(f"❌ Pozycja **{pos}** jest już zajęta!", delete_after=5)
                    await message.add_reaction("❌")
                    return

                for p, u in data["signups"].items():
                    if u == user_mention:
                        data["signups"][p] = None

                data["signups"][pos] = user_mention
                await update_content_embed(thread_id)
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")
            return

import os

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ Brak tokena bota w zmiennych środowiskowych!")