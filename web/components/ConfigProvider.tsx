"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";

export type LlmMode = "fake" | "real" | "unknown";

type Config = {
  llm_mode: LlmMode;
  model: string;
};

const ConfigContext = createContext<Config>({
  llm_mode: "unknown",
  model: "",
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Config>({
    llm_mode: "unknown",
    model: "",
  });

  useEffect(() => {
    let cancelled = false;
    void api<Config>("/config")
      .then((data) => {
        if (!cancelled && (data.llm_mode === "fake" || data.llm_mode === "real")) {
          setConfig(data);
        }
      })
      .catch(() => {
        /* pill stays unknown; playgrounds still work */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>
  );
}

export function useLlmConfig() {
  return useContext(ConfigContext);
}
