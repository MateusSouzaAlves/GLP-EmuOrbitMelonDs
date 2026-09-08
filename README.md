# Código-fonte correspondente do componente Nintendo DS

Este repositório contém somente o código-fonte correspondente ao componente de
Nintendo DS distribuído pelo EmuOrbit Advance, incluindo as modificações e os
scripts usados para gerar o módulo nativo protegido. Ele não contém o aplicativo
Android hospedeiro, jogos, BIOS, firmware, saves, chaves, mapas privados,
telemetria, monetização, recursos visuais ou dados pessoais.

Esta é uma versão modificada dos projetos upstream. As modificações desta
distribuição foram consolidadas em **8 de setembro de 2026** e estão nos
diretórios `melondscore`, `cmake` e `scripts`.

## Licença e origem

O conjunto é distribuído sob a **GNU General Public License versão 3 ou
posterior**, conforme os arquivos `LICENSE` dos projetos e a licença na raiz.

- `third_party/melonds`: melonDS no commit
  `7117178c2dd56df32b6534ba6a54ad1f8547e693`;
- `third_party/melonds-ds`: frontend melonDS DS no commit
  `bc4e4b67d2d470d7c682810a1e892cafd6f9082b`;
- `melondscore`, `cmake` e `scripts`: integração e modificações usadas na
  compilação do componente distribuído.

Os dois projetos upstream são submódulos Git. Clone recursivamente ou execute:

```bash
git submodule update --init --recursive
```

## Requisitos de compilação

- JDK 17;
- Android SDK 37;
- Android NDK `29.0.14206865`;
- CMake `3.22.1` instalado pelo Android SDK;
- Python 3;
- Git.

Defina `ANDROID_HOME` ou `sdk.dir` em um `local.properties` ignorado pelo Git
para apontar para a instalação local do Android SDK.

O build usa somente `arm64-v8a`, a ABI distribuída pelo aplicativo. No Windows:

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat :melondscore:assembleRelease
```

Em Linux/macOS:

```bash
./gradlew :melondscore:assembleRelease
```

O Gradle cria uma seed descartável por invocação. Para uma reconstrução
determinística de diagnóstico, use uma seed ASCII de 8 a 128 caracteres:

```powershell
.\gradlew.bat :melondscore:assembleRelease -PEMUORBIT_BUILD_SEED=source-build-0001
```

As saídas ficam em `melondscore/build/`. A árvore upstream é copiada para essa
pasta antes da aplicação das correções; os submódulos fixados não são alterados.

## Escopo das modificações

- correções de acesso desalinhado usadas pelos diagnósticos nativos;
- redução de mensagens e identificadores não funcionais no binário final;
- codificação temporária de literais funcionais, com limpeza após o uso;
- ocultação de símbolos, ThinLTO, strip, RELRO, NOW, NX e exportação mínima;
- nomes e layout diversificados por build;
- empacotamento do ELF em contêiner autenticado para integração no aplicativo.

Os mecanismos de proteção não mudam os direitos concedidos pela GPL. O código
gerado pode ser estudado, modificado e redistribuído nos termos da licença.

## Correspondência com uma versão distribuída

O commit deste repositório e os dois gitlinks acima identificam a fonte. Uma
publicação do aplicativo deve registrar o commit público correspondente àquela
versão. Nenhum binário comercial, ROM ou dado do usuário é necessário para
compilar este componente.
