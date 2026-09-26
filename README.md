# Código-fonte correspondente — Nintendo DS

Este repositório contém a fonte, os patches e os scripts que geram o
componente Nintendo DS distribuído pelo EmuOrbit Advance. A revisão marcada
por `gpl-source-2026-09-26` é uma fonte de distribuição ativa: ela não é um
protótipo, uma prova local nem uma amostra experimental.

O pacote não contém ROMs, BIOS, firmware, chaves, saves, credenciais,
telemetria, monetização, dados de usuário ou binários pré-compilados.

## Escopo e origem

O componente é distribuído sob **GNU GPL versão 3 ou posterior**.

- `third_party/melonds`: melonDS em
  `7117178c2dd56df32b6534ba6a54ad1f8547e693`;
- `third_party/melonds-ds`: frontend melonDS DS em
  `bc4e4b67d2d470d7c682810a1e892cafd6f9082b`;
- `melondscore`, `cmake` e `scripts`: integração, patches e empacotamento do
  core ARM64;
- [EmuOrbit Advance, tag `gpl-source-2026-09-26`](https://github.com/MateusSouzaAlves/EmuOrbit-Advance/tree/gpl-source-2026-09-26): bridge JNI/libretro e
  integração Android que carregam este componente na distribuição final.

Os dois upstreams são submódulos Git. Após clonar, execute:

```bash
git submodule update --init --recursive
```

## Compilação

Requisitos: JDK 17, Android SDK 37, Android NDK `29.0.14206865`, CMake
`3.22.1`, Python 3 e Git. Defina `ANDROID_HOME` ou `sdk.dir` em um
`local.properties` não versionado.

O componente usa apenas `arm64-v8a`. No Windows:

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat :melondscore:assembleRelease -PEMUORBIT_BUILD_SEED=source-build-0001
```

As saídas ficam em `melondscore/build/`. A árvore upstream é copiada para a
build antes das correções; os submódulos fixados não são alterados.

## Fonte correspondente e publicação

`CORRESPONDING_SOURCE.json` registra a composição da fonte. Para cada novo
artefato distribuído, publique primeiro uma tag de fonte, registre a URL, a
tag, os commits dos upstreams e o hash do binário no repositório do app, e
mantenha essa fonte disponível enquanto o artefato for distribuído.

Os mecanismos de hardening e o contêiner autenticado não alteram os direitos
da GPL: a fonte pode ser estudada, modificada e redistribuída nos termos da
licença.
