/*
  ==============================================================================
  SleepStim_CONFIG.h — Fichier de configuration du protocole SleepStim v4
  ==============================================================================
  Seul ce fichier doit être modifié entre les sessions / rats.
  Le fichier .ino principal ne doit pas être touché.

  Pour modifier un paramètre : changez uniquement la valeur après le `#define`
  ou dans les tableaux `const`, sans toucher au nom de la variable ni aux
  commentaires de structure (lignes `// ──`).
  ==============================================================================
*/

#ifndef SLEEPSTIM_CONFIG_H
#define SLEEPSTIM_CONFIG_H

// ── Commande SysEx custom ─────────────────────────────────────────────────────
// 0x7F et 0x7E sont dans la plage réservée "utilisateur" de la spec Firmata.
// Ne pas modifier sauf collision avec une autre commande SysEx custom.
#define SYSEX_CMD_START  0x7F   // commande custom : démarrer la session
#define SYSEX_CMD_STOP   0x7E   // commande custom : arrêter la session

// Commandes SysEx PAUSE / RESUME (plage réservée utilisateur Firmata)
#define SYSEX_CMD_PAUSE   0x7D
#define SYSEX_CMD_RESUME 0x7C

// ── Broches ───────────────────────────────────────────────────────────────────
// instructionPin : entrée TTL depuis Open-Ephys (signal réveil/immobile)
// stimulationPin : sortie gate vers le générateur Agilent 33250A (Trig In)
#define instructionPin  13
// Broche recevant le TTL de synchronisation depuis Open-Ephys au lancement session.
// Même broche que instructionPin si le TTL de sync passe par le même câble
#define syncPin  13

#define stimulationPin  11

// ── Paramètres temporels du protocole ─────────────────────────────────────────
// Toutes les durées sont en millisecondes (ms).

// Durée totale d'immobilité cumulée à atteindre avant de démarrer la phase STIM.
// L'accumulation se met en pause dès que le rat est éveillé (voir anti-bruit ci-dessous).
#define BASELINE_CUMUL_MS       1800000UL  // 30 min d'immobilité cumulée

// Durée d'immobilité CONTINUE requise avant de déclencher un nouveau bloc de stimulation.
// Si le rat se réveille avant ce délai, le compteur recommence à 0.
#define PRE_STIM_WAIT_MS         120000UL  // 2 min d'immobilité continue avant bloc

// Pause fixe entre deux blocs de stimulation consécutifs (pendant l'immobilité).
#define INTER_BLOCK_PAUSE_MS      60000UL  // 1 min entre blocs

// Intervalle d'immobilité cumulée entre deux logs de progression de la baseline.
// Purement informatif, n'affecte pas la logique du protocole.
#define BASELINE_LOG_INTERVAL     10000UL  // log progression toutes les 10 s cumulées

// ── Paramètres anti-bruit de détection du réveil ──────────────────────────────
// Évite qu'un TTL bref et isolé (artefact) soit interprété comme un réveil réel.
// Le signal TTL brut est intégré sur une fenêtre glissante WINDOW_MS ; si le temps
// cumulé HIGH dans cette fenêtre dépasse K_MS, l'état "pre_wake" est activé.
// Le réveil n'est confirmé que si "pre_wake" persiste PRE_WAKE_CONFIRM_MS.
// Le sommeil n'est confirmé que si "pre_wake" disparaît pendant SLEEP_CONFIRM_MS.

#define WINDOW_MS          7000UL   // fenêtre d'intégration du TTL (ms)
#define K_MS               1000UL   // seuil : TTL intégré > K_MS → pre_wake
#define PRE_WAKE_CONFIRM_MS 5000UL  // pre_wake continu >= 5s → wake confirmé
#define SLEEP_CONFIRM_MS   8000UL   // absence de pre_wake >= 8s → sleep confirmé

// ── Définition des blocs de stimulation ───────────────────────────────────────
// À chaque période d'immobilité (après PRE_STIM_WAIT_MS), un bloc est tiré au
// hasard parmi A, B, C, D et exécuté en entier (sauf réveil, qui l'interrompt).

// Bloc A : 4 durées de stimulation mélangées aléatoirement à chaque tirage,
// chacune suivie d'une pause fixe BLOCK_A_OFF_MS.
const unsigned long BLOCK_A_DURATIONS[4] = { 100, 150, 200, 300 };  // ms, durées possibles
const unsigned long BLOCK_A_OFF_MS       = 60000UL;                 // pause après chaque stim (ms)
const uint8_t       BLOCK_A_REPS         = 4;                       // nombre de répétitions (= taille du tableau)

// Bloc B : 10 répétitions de 100 ms ON / 5 s OFF
const unsigned long BLOCK_B_ON_MS  = 100;
const unsigned long BLOCK_B_OFF_MS = 5000;
const uint8_t       BLOCK_B_REPS   = 10;

// Bloc C : 10 répétitions de 100 ms ON / 10 s OFF
const unsigned long BLOCK_C_ON_MS  = 100;
const unsigned long BLOCK_C_OFF_MS = 10000;
const uint8_t       BLOCK_C_REPS   = 10;

// Bloc D : 10 répétitions de 100 ms ON / 20 s OFF
const unsigned long BLOCK_D_ON_MS  = 100;
const unsigned long BLOCK_D_OFF_MS = 20000;
const uint8_t       BLOCK_D_REPS   = 10;

#endif // SLEEPSTIM_CONFIG_H
