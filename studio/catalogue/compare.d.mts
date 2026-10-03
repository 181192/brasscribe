export type Comparison = { screens: number; changed: string[]; added: string[]; gone: string[] };
export function compare(beforeDir: string, afterDir: string, reportDir: string): Promise<Comparison>;
