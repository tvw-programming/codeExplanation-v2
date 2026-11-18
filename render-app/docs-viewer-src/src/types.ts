export type DocEntry = {
  file: string;
  title: string;
};

export type DocGroup = {
  group: string;
  items: DocEntry[];
};
