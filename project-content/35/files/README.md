# Intercom

Deux crates Rust :

- [`intercom/`](intercom/README.md) : l'application de bureau (soundboard, changeur de voix en direct, auto-clic et dérive de la souris), pour Linux et Windows.
- [`voice-changer/`](voice-changer/README.md) : les effets de voix (hauteur, robot, voix de console), utilisés par Intercom comme bibliothèque, et un programme en ligne de commande qui mesure leur latence et leur charge CPU.

Intercom dépend de `voice-changer` par un chemin relatif (`../voice-changer`) : gardez les deux dossiers côte à côte, puis, depuis `intercom/` :

```
cargo run --release
```

Les instructions complètes (dépendances, installation, micro virtuel, permissions) sont dans chaque README.
